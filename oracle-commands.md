# Команды для развёртывания в Oracle Cloud

Подключись к серверу: `ssh -i путь/к/ключу.key ubuntu@ТВОЙ_IP`

Дальше на сервере выполни по порядку.

---

## 1. Установка и клонирование

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
cd ~
git clone https://github.com/DanilTimoshenko/tutor-bot.git
cd tutor-bot
```

## 2. Окружение Python

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Конфиг

```bash
nano config.py
```

Вставь (подставь свой токен и ID):

```python
BOT_TOKEN = "сюда_токен_от_BotFather"
TUTOR_USER_ID = 123456789
BOT_TITLE = None
MATERIALS_CHANNEL_LINK = None
CHANNEL_ID = None
SUMMARY_DAILY_HOUR = 9
```

Сохрани: Ctrl+O, Enter, Ctrl+X.

## 4. Служба

```bash
sudo cp tutor-bot-ubuntu.service /etc/systemd/system/tutor-bot.service
sudo systemctl daemon-reload
sudo systemctl enable tutor-bot
sudo systemctl start tutor-bot
sudo systemctl status tutor-bot
```

Должно быть `active (running)`.

## Потом: обновление бота

```bash
cd ~/tutor-bot
git pull
sudo systemctl restart tutor-bot
```
