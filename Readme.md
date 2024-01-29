# Pgbackuper - инструмент для автоматизированного снятия pg_dump по расписанию

Предполагается использования внутри контейнера docker.
По заданному расписанию инструмент снимает pg_dump с базы данных (одной или нескольких), сохраняет файл pg_dump в `/var/pgpackup`, при указании настроек подключения к WebDAV отправляет дополнительно файлы на сервер.
При необходимости очистка старых файлов регулируется политикой удержания (по умолчанию: старые файлы не удаляются, при выставлении переменной `RETENTION`: будет сохранено установленное число последних файлов для каждой базы данных).

## Переменные окружения:

### Основные

* `LOG_LEVEL` (int) = `20` (10 - DEBUG, 20 - INFO, 30 - WARN, 40 - ERROR, 50 - CRITICAL)
* `INTERVAL_CRON` (str cron) = `"45 23 * * *"`

* `PGDATABASE` (str) имя базы данных (можно указать несколько, через запятую)
* `PGHOST` (str) сервер Postgres, без указания номера порта (может быть IP-адрес или DNS-имя)
* `PGPORT` (int) = `5432` порт Postgres
* `PGUSER` (str) имя пользователя, с которым будет выполняться подключение к Postgres
* `PGPASSWORD` (str) пароль, с которым будет выполняться подключение к Postgres
* `PGPASSFILE` (str) = `~/.pgpass` более безопасный способ передачи пароля, файл в формате `сервер:порт:база_данных:имя_пользователя:пароль`, вместо первых параметров может содержать `*`, права должны быть u=rw (0600), подробнее: [postgresql.org/docs/current/libpq-pgpass.html](https://www.postgresql.org/docs/current/libpq-pgpass.html)
* `PGFORMAT` = `plain` формат файла pg_dump (может быть: `plain`, `custom`, `tar`), подробнее: [postgresql.org/docs/current/app-pgdump.html](https://www.postgresql.org/docs/current/app-pgdump.html)

### Дополнительные

* `RETENTION` (int) = `0` политика удержания: сколько последних файлов pg_dump требуется хранить, `0` - отключает удаление, значение больше нуля включает удаление старых файлов pg_dump, сохраняется кол-во файлов, соответствующих значению переменной

* `WEBDAV_URL` (str) URL (полностью) WebDAV сервера, на который следует загружать файлы pg_dump, например `https://webdav.yandex.ru` или `https://nextcloud.example.com`
* `WEBDAV_USER` (str) имя пользователя WebDAV
* `WEBDAV_PATH` (str) путь к папке на сервере WebDAV (для Nextcloud: `/remote.php/dav/files/WEBDAV_USER/имя_папки`, где `WEBDAV_USER` и `имя_папки` заменить на значения)
* `WEBDAV_PASSWORD` | `WEBDAV_PASSWORD_FILE` (str) пароль WebDAV, можно задать ввиде пути к файлу, содержащему пароль

*  `TZ` (str) = `UTC` имя Timezone, например `Europe/Moscow` (повлияет на указание времени создания в именах файлов pg_dump) 

## Примеры

### Быстрый старт

```
services:
  pgbackup:
    image: skl256/pgbackuper:latest
    environment:
      INTERVAL_CRON: "45 23 * * *" # daily, at 23:45
      PGDATABASE: "postgres"
      PGHOST: "192.168.1.103"
      PGUSER: "postgres"
      PGPASSWORD: "postgres"
```

### Расширенный (с использованием WebDAV, docker secrets in swarm mode)
```
services:
  pgbackup:
    image: skl256/pgbackuper:latest
    environment:
      INTERVAL_CRON: "45 23 * * *" # daily, at 23:45
      PGDATABASE: "postgres, nextcloud" # pg_dump databases "postgres", "nextcloud"
      PGHOST: "192.168.1.103"
      PGUSER: "postgres"
      PGPASSFILE: "/var/run/secrets/pgpassfile"
      RETENTION: 3
      WEBDAV_URL: "https://webdav.example.com"
      WEBDAV_USER: "skl256"
      WEBDAV_PATH: ""
      WEBDAV_PASSWORD_FILE: "/var/run/secrets/webdav_password" # mode must be 0600, in compose use volume mount instead secret for this file
    volumes:
      - pg_dumps:/var/pgbackup
    secrets:
      - source: pgpassfile
        target: pgpassfile
        uid: "0"
        gid: "0"
        mode: 0600
      - webdav_password
secrets:
  pgpassfile:
    external: true # works only in docker swarm, not in compose
  webdav_password:
    file: webdav_password.txt
volumes:
  pg_dumps:
```
(в данном примере созданы секреты docker и файл с паролем от WebDAV: `echo '*:*:*:*:postgres' | docker secret create pgpassfile -; echo 'example_password' > webdav_password.txt`)
  