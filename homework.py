import logging
import sys
import os
import time
from pathlib import Path

from exceptions import ServiceError, EndpointError,\
    MessageSendingError, NotForSend, DataTypeError, ResponseFormatError

import requests
import telegram

from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

CONNECTION_ERROR = 'Ошибка соединения: {error}, {url}, {headers}, {params}'
SERVICE_REJECTION = 'Отсутствует доступ к эндпоинту {code}'
WRONG_ENDPOINT = 'Некорректный эндпоинт {response_status}, {url},\
                                        {headers}, {params}'
WRONG_HOMEWORK_STATUS = 'Некорректный статус {homework_status}'
WRONG_DATA_TYPE = 'Неверный тип данных {type}, вместо "dict"'
WRONG_HOMEWORK_NAME = 'Некорректное ключ {homework_name}'
STATUS_IS_CHANGED = 'Статус работы изменился {verdict}, {homework}'
STATUS_IS_NOT_CHANGED = 'Статус не изменился, нет записей'
FAILURE_TO_SEND_MESSAGE = 'Ошибка при отправке сообщения {error}, {message}'
GLOBAL_VARIABLE_IS_MISSING = 'Отсутствует глобальная переменная'
GLOBAL_VARIABLE_IS_EMPTY = 'Пустая глобальная переменная'
MESSAGE_IS_SENT = 'Сообщение {message} отправлено'
FORMAT_NOT_JSON = 'Формат не json {error}'
LIST_IS_EMPTY = 'Список пуст'

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение пользователю в Телегу."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as error:
        raise MessageSendingError(FAILURE_TO_SEND_MESSAGE.format(
            error=error,
            message=message,
        ))
    logging.info(f'Message "{message}" is sent')


def get_api_answer(current_timestamp):
    """Получает ответ от API."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    all_params = dict(url=ENDPOINT, headers=HEADERS, params=params)
    try:
        response = requests.get(**all_params)
    except requests.exceptions.RequestException as error:
        raise telegram.TelegramError(CONNECTION_ERROR.format(
            error=error,
            **all_params,
        ))
    response_status = response.status_code
    if response_status != 200:
        raise EndpointError(WRONG_ENDPOINT.format(
            response_status=response_status,
            **all_params,
        ))
    try:
        return response.json()
    except Exception as error:
        raise ResponseFormatError(FORMAT_NOT_JSON.format(error))


def check_response(response):
    """
    Возвращает домашку, если есть.
    Проверяет валидность её статуса.
    """
    if not isinstance(response, dict):
        raise TypeError('Ошибка в типе ответа API')
    if 'homeworks' not in response or 'current_date' not in response:
        raise ServiceError(SERVICE_REJECTION)
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise KeyError('Homeworks не является списком')
    return homeworks


def parse_status(homework):
    """Возвращает текст сообщения от ревьюера."""
    if not isinstance(homework, dict):
        raise DataTypeError(WRONG_DATA_TYPE.format(type(homework)))
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if 'homework_name' not in homework:
        raise KeyError(WRONG_HOMEWORK_NAME)
    if homework_status not in HOMEWORK_STATUSES:
        raise NameError(WRONG_HOMEWORK_STATUS.format(homework_status))

    verdict = HOMEWORK_STATUSES[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    logging.info('Проверка наличия всех токенов')
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ENDPOINT])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit('Ошибка глобальной переменной. Смотрите логи.')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get(
                'current_date', int(time.time())
            )
            homeworks = check_response(response)
            message = parse_status(homeworks)
            if len(homeworks) > 0:
                parse_status(homeworks[0])
            if message != last_message:
                send_message(bot, message)
                last_message = message
            logging.info(homeworks)
            current_timestamp = response.get('current_date')
            if message == last_message:
                message = 'Статус работы не изменился'
                send_message(bot, message)
                logging.info(message)

        except NotForSend as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != last_message:
                send_message(bot, message)
                last_message = message
            logging.error(message)
        finally:
            time.sleep(RETRY_TIME)
            logging.info(MESSAGE_IS_SENT.format(message))


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s, %(message)s, %(lineno)d, %(name)s',
        filemode='w',
        filename=f'{Path(__file__).stem}.log',
        level=logging.INFO,
    )
    main()
