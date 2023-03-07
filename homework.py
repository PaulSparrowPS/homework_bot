import json
import logging
import os
import requests
import sys
import telegram
import time

from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from logging import StreamHandler
from http import HTTPStatus

from exceptions import (HTTPConnectionError,
                        JSONConvertError,
                        JSONContentError,
                        ParsingError,
                        TelegramError
                        )

load_dotenv()
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

logger = logging.getLogger(__name__)

formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
logger.setLevel(logging.DEBUG)

rf_handler = RotatingFileHandler(
    'homework_bot.log',
    maxBytes=50000,
    backupCount=1
)
rf_handler.setLevel(logging.DEBUG)
rf_handler.setFormatter(formatter)
logger.addHandler(rf_handler)

s_handler = StreamHandler(sys.stdout)
s_handler.setLevel(logging.DEBUG)
s_handler.setFormatter(formatter)
logger.addHandler(s_handler)

RETRY_PERIOD = 10 * 60  # 10 минут
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправка сформированного сообщения в Telegram с помощью бота."""
    logger.info('Начато отправка сообщения.')
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        logger.debug('Успешно отправлено сообщение в Telegram.')
    except Exception as error:
        logger.error(
            f'Боту не удалось отправить сообщение в Telegram. {error}'
        )
        raise TelegramError(
            f'Не удалось отправить сообщение в Telegram. {error}'
        )


def get_api_answer(current_timestamp):
    """Запрос домашек у API Яндекс.Практикума и преобразование в JSON."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException:
        raise HTTPConnectionError('Не удалось получить ответ от API.')
    else:
        logger.info('Ответ от API получен.')

    if response.status_code != HTTPStatus.OK:
        raise HTTPConnectionError('Ответ от API не верный.')

    try:
        response = response.json()
    except json.decoder.JSONDecodeError:
        raise JSONConvertError('Не удалось преобразовать ответ от API в JSON.')
    else:
        logger.info('Ответ от API преобразован в JSON.')

    return response


def check_response(response):
    """Проверка запроса к API на корректность и извлечение списка домашек."""
    try:
        homeworks = response['homeworks']
    except KeyError:
        raise JSONContentError(
            'Ошибка: в ответе API домашки нет необходимых ключей')
    else:
        logger.info('Список домашек в ответе от API получен.')

    if not isinstance(response['homeworks'], list):
        logger.error('В ответе от API нет списка домашек.')
        raise TypeError('В ответе от API нет списка домашек.')

    if homeworks and not isinstance(homeworks[0], dict):
        raise JSONContentError('Содержимое списка домашек некорректно.')

    return homeworks


def parse_status(homework):
    """Получение статуса домашки и формирование сообщения для бота."""
    homework_status = homework.get('status')
    homework_name = homework.get('homework_name')
    if homework_status is None:
        raise ParsingError('Ошибка пустое значение status: ', homework_status)
    if homework_name is None:
        raise ParsingError('Ошибка пустое значение homework_name: ',
                           homework_name)
    try:
        verdict = HOMEWORK_VERDICTS[homework_status]
    except KeyError:
        raise ParsingError('Статус домашней работы не удалось распознать.')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    ENV_VARS = {
        PRACTICUM_TOKEN: 'PRACTICUM_TOKEN',
        TELEGRAM_TOKEN: 'TELEGRAM_TOKEN',
        TELEGRAM_CHAT_ID: 'TELEGRAM_CHAT_ID',
    }

    return all(ENV_VARS)


def main():
    """Основная логика работы бота."""
    logger.info('__Старт программы__')

    if not check_tokens():
        logger.critical('Ошибка в загрузке переменнных')
        sys.exit('Программа завершилась')

    current_timestamp = int(time.time())
    previous_message = None

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.info('Связь с ботом установлена.')

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
            else:
                message = 'Обновлений по домашке нет.'
                logger.debug('Обновлений по домашке нет.')

            if message != previous_message:
                logger.info('Сформировано новое сообщение.')
                send_message(bot, message)
                previous_message = message
            else:
                logger.info('Нет нового сообщения.')

            try:
                current_timestamp = response['current_date']
            except KeyError:
                current_timestamp = int(time.time())
                logger.debug(
                    'Не удалось получить время запроса из ответа от API. '
                    'Для выполнения следующего запроса принято текущее время.'
                )

        except Exception as error:
            current_error = f'Сбой в работе программы: "{error}"'
            logger.error(current_error)
            time.sleep(RETRY_PERIOD)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
