"""Structure validation and optional streamed per-payload hashing."""

import zstandard
from .read import NupReader


def verify(path, deep=True, max_problems=20):
    problems = []
    try:
        with NupReader(path) as reader:
            if deep:
                for index, row in enumerate(reader.files):
                    try:
                        for _ in reader.iter_file_chunks(index):
                            pass
                    except (ValueError, OSError, zstandard.ZstdError) as error:
                        problems.append(f"{row[0].decode('utf-8', 'replace')}: {error}")
                        if len(problems) >= max_problems:
                            break
    except (ValueError, OSError) as error:
        problems.append(str(error))
    return not problems, problems
