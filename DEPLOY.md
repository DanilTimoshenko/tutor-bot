# Запуск бота на сервере (VPS)

Так бот работает 24/7 и не зависит от твоего компьютера.

---

## Развёртывание в Oracle Cloud (по шагам)

### 1. Регистрация и создание VM

1. Зайди на **[cloud.oracle.com](https://www.oracle.com/cloud/free/)** → **Create Free Account**.
2. Нужна карта (списание 0 ₽, только проверка; после создания VM можно отвязать).
3. В консоли Oracle: **Menu** → **Compute** → **Instances** → **Create instance**.
4. Оставь имя по умолчанию или введи своё.
5. **Image and shape:**  
   - Image: **Ubuntu 22.04**  
   - Shape: **VM.Standard.E2.1.Micro** (Always Free).
6. **Add SSH keys:** выбери «Generate a key pair for me», скачай приватный ключ (`.key`) и сохрани. Публичный ключ Oracle подставит сам.
7. Нажми **Create**. Дождись статуса **Running**, скопируй **Public IP address**.

### 2. Подключение к серверу

На Mac открой терминал. Если ключ скачан в `~/Downloads`:

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-XXXX.key ubuntu@PUBLIC_IP
```

(подставь имя файла ключа и IP). Подключишься под пользователем `ubuntu`.

### 3. На сервере — одна цепочка команд

Скопируй и вставь в терминал по блокам (подставь свой **PUBLIC_IP** только там, где написано).

**Установка Python и клонирование проекта:**

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
cd ~
git clone https://github.com/DanilTimoshenko/tutor-bot.git
cd tutor-bot
```

**Виртуальное окружение и зависимости:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Создание config.py** (вставь свой токен и свой Telegram ID):

```bash
nano config.py
```

Вставь (замени токен и ID на свои):

```python
BOT_TOKEN = "твой_токен_от_BotFather"
TUTOR_USER_ID = 123456789   # твой Telegram ID (узнать: @userinfobot)
BOT_TITLE = None
MATERIALS_CHANNEL_LINK = None
CHANNEL_ID = None
SUMMARY_DAILY_HOUR = 9
```

Сохрани: **Ctrl+O**, Enter, **Ctrl+X**.

**Запуск как службы (автозапуск после перезагрузки):**

```bash
sudo cp tutor-bot-ubuntu.service /etc/systemd/system/tutor-bot.service
sudo systemctl daemon-reload
sudo systemctl enable tutor-bot
sudo systemctl start tutor-bot
sudo systemctl status tutor-bot
```

В конце должно быть `active (running)`. Готово: бот работает 24/7.

**Полезные команды на сервере:**

| Действие | Команда |
|----------|--------|
| Смотреть логи в реальном времени | `journalctl -u tutor-bot -f` |
| Перезапустить бота | `sudo systemctl restart tutor-bot` |
| Обновить код с GitHub | `cd ~/tutor-bot && git pull && sudo systemctl restart tutor-bot` |

---

## Бесплатно 24/7 (кратко)

**Oracle Cloud (Always Free)** — сервер бесплатный без ограничения по времени.

**Другие бесплатные варианты (с ограничениями):**

- **Google Cloud** — e2-micro в рамках free tier в подходящем регионе (нужна карта, лимиты трафика).
- **Fly.io** — бесплатный тариф с лимитами; бот можно запустить в контейнере.

Для стабильной работы 24/7 без «засыпания» лучше всего подходит **Oracle Cloud Always Free**.

---

## Платный VPS (если нужен запас по ресурсам)

- **Timeweb**, **Selectel**, **DigitalOcean**, **Hetzner** — от ~100–200 ₽/мес.
- Хватает самого дешёвого варианта (1 GB RAM, 1 CPU).

## Шаг 1: Подключись к серверу

По SSH (подставь свой IP и логин):

```bash
ssh root@IP_АДРЕС_СЕРВЕРА
```

или с ключом:

```bash
ssh -i путь/к/ключу root@IP_АДРЕС_СЕРВЕРА
```

## Шаг 2: Установи Python на сервере

```bash
apt update
apt install -y python3 python3-pip python3-venv
```

## Шаг 3: Залей проект на сервер

**Вариант А — с твоего Mac через SCP** (из папки проекта):

```bash
cd /Users/apple/MyNewProject
scp -r . root@IP_АДРЕС_СЕРВЕРА:/root/tutor-bot/
```

Не копируй папку `.venv` — её лучше собрать на сервере. Исключи её:

```bash
cd /Users/apple/MyNewProject
rsync -avz --exclude '.venv' --exclude 'bot.log' --exclude 'bot.pid' --exclude 'tutor_bot.db' . root@IP_АДРЕС_СЕРВЕРА:/root/tutor-bot/
```

**Вариант Б — через Git:** если проект в GitHub/GitLab, на сервере:

```bash
git clone URL_ТВОЕГО_РЕПОЗИТОРИЯ /root/tutor-bot
cd /root/tutor-bot
```

Потом на сервере создай `config.py` (скопируй с компа или напиши вручную с токеном и TUTOR_USER_ID).

## Шаг 4: На сервере — настрой и запусти бота

```bash
cd /root/tutor-bot

# Виртуальное окружение и зависимости
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Конфиг (если ещё не залит)
nano config.py   # вставь BOT_TOKEN, TUTOR_USER_ID и т.д.

# Запуск в фоне через systemd (перезапуск при падении и после перезагрузки)
# Если проект лежит не в /root/tutor-bot — отредактируй tutor-bot.service (WorkingDirectory и ExecStart)
sudo cp tutor-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tutor-bot
sudo systemctl start tutor-bot
sudo systemctl status tutor-bot
```

Логи:

```bash
journalctl -u tutor-bot -f
```

Остановить/запустить заново:

```bash
sudo systemctl stop tutor-bot
sudo systemctl start tutor-bot
```

## Итог

- Бот крутится на сервере, с твоего компьютера можно вообще не запускать.
- После перезагрузки сервера служба поднимется сама.
- Обновить бота: залей новые файлы (или `git pull`), затем `sudo systemctl restart tutor-bot`.
