# Запуск бота на сервере (VPS)

Так бот работает 24/7 и не зависит от твоего компьютера.

---

## Бесплатно 24/7

**Oracle Cloud (Always Free)** — сервер действительно бесплатный и без ограничения по времени.

- Регистрация: [cloud.oracle.com](https://www.oracle.com/cloud/free/) → Create Free Account.
- Нужна банковская карта (списывают 0 ₽, только проверка; можно отвязать после создания VM).
- В консоли: Create a VM instance → образ **Ubuntu 22.04**, форму **VM.Standard.E2.1.Micro** (1 GB RAM) — она входит в Always Free.
- После создания скопируй **Public IP**, подключись по SSH (логин по умолчанию `ubuntu`):

  ```bash
  ssh ubuntu@IP_АДРЕС
  ```

Дальше действуй по шагам ниже. Папку на сервере можно сделать в домашнем каталоге, например `~/tutor-bot`, и в `tutor-bot.service` указать путь `/home/ubuntu/tutor-bot` и пользователя `ubuntu` (и сменить в сервисе `User=ubuntu`).

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
