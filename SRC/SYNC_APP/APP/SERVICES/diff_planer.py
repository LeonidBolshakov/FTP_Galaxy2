from pathlib import Path

from SRC.SYNC_APP.APP.dto import (
    DiffPlan,
    DiffInput,
    InvalidFile,
    FileSnapshot,
)


class DiffPlanner:
    """Строит план синхронизации локальной директории с удалённым (FTP).

    Назначение:
        — определить, какие файлы нужно удалить локально (лишние),
        — какие нужно скачать (отсутствуют локально),
        — какие присутствуют в обоих местах, но отличаются по размеру/хэшу.

    Важно:
        Сравнение производится по *имени файла* (basename), без учёта каталогов.
        Для remote-части ключи нормализуются как Path(remote_path).name.
        Это означает, что два разных remote-пути с одинаковым basename считаются конфликтом.
    """

    def run(self, data: DiffInput) -> DiffPlan:
        """Сравнивает локальные и удалённые файлы и возвращает DiffPlan.

        Алгоритм:
            1) Берёт локальные файлы как есть: `data.local.files` (dict[name -> FileSnapshot]).
            2) Преобразует удалённые файлы к словарю `basename -> FileSnapshot`.
               При обнаружении двух remote-файлов с одинаковым basename — бросает ValueError.
            3) По множествам ключей вычисляет:
               - to_delete   = local - remote
               - to_download = remote - local
               - common      = local ∩ remote
            4) Для common сравнивает пары FileSnapshot по size и md5_hash и формирует список InvalidFile.

        Args:
            data: DiffInput, содержащий два снимка: local и remote.

        Returns:
            DiffPlan:
                - to_delete: отсортированный список имён, которые есть локально, но отсутствуют на сервере;
                - to_download: отсортированный список имён, которые есть на сервере, но отсутствуют локально;
                - diff_files: список расхождений для файлов, присутствующих в обоих снимках.

        Raises:
            ValueError: если на удалённой стороне обнаружены два файла с одинаковым basename,
                        что делает сравнение по имени неоднозначным.
        """
        local_dict_files = data.local.files

        remote_items = [(Path(p).name, snap) for p, snap in data.remote.files.items()]

        remote_dict_files: dict[str, FileSnapshot] = {}
        for name, snap in remote_items:
            if name in remote_dict_files:
                raise ValueError(
                    "Ошибка в программе. Из каталога FTP считано 2 одинаковых имени:\n"
                    f"{name}"
                )
            remote_dict_files[name] = snap

        local_names = set(local_dict_files)
        remote_names = set(remote_dict_files)

        common_names = local_names & remote_names

        delete = local_names - remote_names
        to_delete: list[FileSnapshot] = []
        for file_name in delete:
            to_delete.append(local_dict_files[file_name])

        download = remote_names - local_names
        to_download: list[FileSnapshot] = []
        for file_name in download:
            to_download.append(remote_dict_files[file_name])

        diff_files: list[InvalidFile] = []
        for file_name in sorted(common_names):
            local = local_dict_files[file_name]
            remote = remote_dict_files[file_name]

            if local.size != remote.size:
                diff_files.append(
                    InvalidFile(
                        file_name,
                        f"Размеры: local={local.size}, remote={remote.size}",
                    )
                )

            if local.md5_hash != remote.md5_hash:
                diff_files.append(
                    InvalidFile(
                        file_name,
                        f"Хэш файла: local={local.md5_hash}, remote={remote.md5_hash}",
                    )
                )

        return DiffPlan(
            to_delete=sorted(to_delete, key=lambda f: f.name),
            to_download=sorted(to_download, key=lambda f: f.name),
            diff_files=sorted(diff_files, key=lambda f: f.name),
        )
