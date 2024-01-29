import datetime
import logging
import os
import re
import shlex
import subprocess
import webdav3.client
from getenv2.getenv2 import getenv

class Pgbackup:
    FILENAME = "Pgbackup_{pghost}_{pgport}_{pgdatabase}_{Ymd_HMS}.{pgformat_ext}"
    LOCAL_PATH = "/var/pgbackup" # "." = script workdir

    def __init__(self):
        if os.getenv("PGDATABASE") is None:
            logging.error("PGDATABASE variable is not set; EXIT.")
            exit(1)
        else:
            self.pgdatabases = list(
                obj.strip() for obj in os.getenv("PGDATABASE").split(",")
            )

        if os.getenv("PGHOST") is None:
            logging.error("PGHOST variable is not set; EXIT.")
            exit(1)
        else:
            self._pghost = os.getenv("PGHOST").strip()

        if os.getenv("PGPORT") is None:
            logging.debug("PGPORT variable is not set; The default port 5432 will be used.")
            self._pgport = 5432
        else:
            self._pgport = int(os.getenv("PGPORT").strip())

        if os.getenv("PGUSER") is None:
            logging.warning("PGUSER variable is not set; the username from the container will be used to connect to " +
                            "the database.")

        if os.getenv("PGPASSWORD") is None and os.getenv("PGPASSFILE") is None:
            logging.warning("PGPASSWORD or PGPASSFILE variables is not set; Are you sure that you specified a " +
                            "password to connect to the database?")

        if os.getenv("PGFORMAT") is None:
            logging.debug("PGFORMAT variable is not set; The default format \"plain\" will be used.")
            self._pgformat = "plain"
        else:
            self._pgformat = os.getenv("PGFORMAT").strip().lower()

        if self._pgformat not in ("plain", "custom", "tar"):
            logging.error("Incorrect PGFORMAT. Only \"plain\", \"custom\", \"tar\" formats supported.")
            exit(1)

        if os.getenv("RETENTION") is None:
            logging.warning("Retention policy is disabled. Old backups will not be deleted. To enable the retention " +
                            "policy, set RETENTION variable (see Readme.md).")
            self.retention = 0
        else:
            self.retention = int(os.getenv("RETENTION").strip())

        if os.getenv("WEBDAV_URL") is None or os.getenv("WEBDAV_USER") is None or getenv("WEBDAV_PASSWORD") is None:
            logging.warning("WebDAV settings are not configured; backups will only be saved in the local filesystem.")
            self.webdav_options = None
        else:
            self.webdav_options = {
                "webdav_hostname": os.getenv("WEBDAV_URL").strip(),
                "webdav_login": os.getenv("WEBDAV_USER").strip(),
                "webdav_password": getenv("WEBDAV_PASSWORD"),
            }

            if os.getenv("WEBDAV_PATH") is None:
                logging.warning("WEBDAV_PATH variable is not set; The root WebDAV directory will be used.")
                self.webdav_path = ""
            else:
                self.webdav_path = os.getenv("WEBDAV_PATH").strip()

        if not os.path.exists(Pgbackup.LOCAL_PATH):
            try:
                os.mkdir(path=Pgbackup.LOCAL_PATH, mode=700)
                logging.info(
                    "Directory for pg_dumps \"{local_path}\"did not exist and was created.".format(
                        local_path=Pgbackup.LOCAL_PATH
                    )
                )
            except BaseException as ex:
                logging.error(
                    ("Directory for pg_dumps \"{local_path}\" did not exist. " +
                     "An error occurred while trying to create: {exception}; "+
                     "Please create the directory manually, and make sure that the program has rw permissions to " +
                     "the directory. EXIT.").format(
                        local_path=Pgbackup.LOCAL_PATH,
                        exception=str(ex)
                    )
                )
                exit(1)

        try:
            os.chdir(Pgbackup.LOCAL_PATH)
        except BaseException as ex:
            logging.error(
                "Can't change to working directory: {exception}; EXIT.".format(exception=str(ex))
            )
            exit(1)

    def start(self):
        logging.info(
            "Will be created from the server \"{pghost}:{pgport}\" backups of databases: {pgdatabases} ...".format(
                pghost=self._pghost,
                pgport=self._pgport,
                pgdatabases=", ".join(self.pgdatabases)
            )
        )

        for pgdatabase in self.pgdatabases:
            pg_dump_filename = self.pg_dump(pgdatabase)

            if pg_dump_filename is None:
                continue

            if self.webdav_options is not None:
                pg_dump_webdav_filename = self.upload_to_webdav(pg_dump_filename)

            self.retention_policy(pgdatabase)

    def pg_dump(self, pgdatabase):
        logging.info(
            "Starting pg_dump for database \"{pgdatabase}\" ...".format(pgdatabase=pgdatabase)
        )

        filename = Pgbackup.FILENAME.format(
            pghost=self._pghost,
            pgport=self._pgport,
            pgdatabase=pgdatabase,
            Ymd_HMS=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            pgformat_ext="sql" if self._pgformat == "plain" else self._pgformat
        )

        cmd = \
            "pg_dump --dbname=\"{pgdatabase}\" --no-password --file=\"{filename}\" --format=\"{pgformat}\"".format(
                pgdatabase=shlex.quote(pgdatabase),
                filename=shlex.quote(filename),
                pgformat=shlex.quote(self._pgformat)
            )

        logging.debug("Command running: {cmd}".format(cmd=cmd))

        result = subprocess.run(shell=True, args=cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')

        if result.returncode != 0:
            logging.error(
                "An error occurred while creating database \"{pgdatabase}\" dump: {stderr}".format(
                    pgdatabase=pgdatabase,
                    stderr=result.stderr.strip()
                )
            )

            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    logging.debug(
                        "Because the pg_dump was not created, the file \"{filename}\" was deleted.".format(
                            filename=filename
                        )
                    )
            except BaseException as ex:
                logging.warning(
                    "An attempt to delete a pg_dump file \"{filename}\" failed with an error: {exception}".format(
                        filename=filename,
                        exception=str(ex)
                    )
                )

            return None

        if not os.path.exists(filename):
            logging.error(
                "An error occurred while creating database \"{pgdatabase}\" dump file.".format(
                    pgdatabase=pgdatabase
                )
            )
            return None

        logging.info(
            "Completed pg_dump for database \"{pgdatabase}\", created file \"{filename}\" size {filesize} bytes.".
            format(
                pgdatabase=pgdatabase,
                filename=filename,
                filesize=os.path.getsize(filename)
            )
        )

        return filename

    def upload_to_webdav(self, filename):
        if self.webdav_options is None:
            logging.debug("Execution of function \"upload_to_webdav\" will be skipped, because WebDAV settings " +
                          "are not configured.")
            return None

        webdav_client = webdav3.client.Client(self.webdav_options)

        try:
            webdav_client.upload_sync(
                local_path=filename,
                remote_path=self.webdav_path + "/" + filename
            )
            logging.info(
                "File \"{filename}\" was successfully sent to the WebDAV server.".format(
                    filename=filename
                )
            )
        except BaseException as ex:
            logging.error(
                "An error occurred while sending file \"{filename}\" to the WebDAV server: {exception}".format(
                    filename=filename,
                    exception=str(ex).strip()
                )
            )
            return None

        return filename

    def _last_backups_list(self, source, pattern):
        if source == "local":
            return self._last_backups_list_local(pattern)
        elif source == "webdav":
            return self._last_backups_list_webdav(pattern)
        else:
            raise Exception("Unknown source for getting list of files: {source}".format(source=source))

    @staticmethod
    def _last_backups_list_local(pattern):
        last_backups_list_local = sorted(
            (obj for obj in os.listdir() if re.fullmatch(pattern, obj)),
            reverse=True
        )

        return last_backups_list_local

    def _last_backups_list_webdav(self, pattern):
        if self.webdav_options is None:
            logging.debug("Execution of function \"_last_backups_list_webdav\" will be skipped, because WebDAV " +
                          "settings are not configured.")
            return None

        webdav_client = webdav3.client.Client(self.webdav_options)

        try:
            last_backups_list_webdav = sorted(
                (obj for obj in webdav_client.list(self.webdav_path) if re.fullmatch(pattern, obj)),
                reverse=True
            )
        except BaseException as ex:
            logging.error(
                "An error occurred while retrieving a list of files from the WebDAV server: {exception}".format(
                    exception=str(ex).strip()
                )
            )
            return []

        return last_backups_list_webdav

    def _delete(self, source, filename):
        if source == "local":
            return self._delete_local(filename)
        elif source == "webdav":
            return self._delete_webdav(filename)
        else:
            raise Exception("Unknown source for delete file: {source}".format(source=source))

    @staticmethod
    def _delete_local(filename):
        try:
            os.remove(filename)
        except BaseException as ex:
            logging.error(
                "An error occurred while removing local file \"{filename}\": {exception}".format(
                    filename=filename,
                    exception=str(ex)
                )
            )
            return False

        return True

    def _delete_webdav(self, filename):
        if self.webdav_options is None:
            logging.debug("Execution of function \"_delete_webdav\" will be skipped, because WebDAV " +
                          "settings are not configured.")
            return False

        webdav_client = webdav3.client.Client(self.webdav_options)

        try:
            webdav_client.clean(self.webdav_path + "/" + filename)
        except BaseException as ex:
            logging.error(
                "An error occurred while removing webdav file \"{filename}\": {exception}".format(
                    filename=filename,
                    exception=str(ex).strip()
                )
            )
            return False

        return True


    def retention_policy(self, pgdatabase):
        if self.retention == 0:
            logging.debug("Execution of function \"retention_policy\" will be skipped, because retention policy " +
                          "is disabled.")
            return None

        pattern = \
            "^" + \
            Pgbackup.FILENAME.format(
                pghost=re.escape(self._pghost),
                pgport=self._pgport,
                pgdatabase=re.escape(pgdatabase),
                Ymd_HMS="\\d{8}_\\d{6}\\",
                pgformat_ext="(sql|custom|tar|aes)"
            ) + \
            "$"

        sources = ["local"]
        if self.webdav_options is not None:
            sources.append("webdav")

        for source in sources:
            last_backups_list = self._last_backups_list(source, pattern)

            if len(last_backups_list) <= self.retention:
                logging.info(
                    ("In {source} filesystem {len_last_backup_list} files matching the pattern were found, " +
                    "the retention policy allows {retention} files to be stored.").format(
                        source=source,
                        len_last_backup_list=len(last_backups_list),
                        retention=self.retention
                    )
                )
            else:
                logging.info(
                    ("In {source} filesystem {len_last_backup_list} files matching the pattern were found, " +
                    "the retention policy allows {retention} files to be stored. " +
                    "{will_be_deleted} files will be deleted.").format(
                        source=source,
                        len_last_backup_list=len(last_backups_list),
                        retention=self.retention,
                        will_be_deleted=len(last_backups_list)-self.retention
                    )
                )

                i = self.retention
                while i < len(last_backups_list):
                    if self._delete(source, last_backups_list[i]):
                        logging.info(
                            "File \"{filename}\" was deleted from the {source} filesystem.".format(
                                source=source,
                                filename=last_backups_list[i]
                            )
                        )
                    i += 1
