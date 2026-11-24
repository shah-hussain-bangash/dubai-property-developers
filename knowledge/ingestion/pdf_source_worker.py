"""Short-lived PDF text parser. Binary originals are never persisted."""

import io
import json
import sys


def main() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    from pypdf import PdfReader

    try:
        data = sys.stdin.buffer.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError()
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError()
        pages = []
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > 5_000_000:
                raise ValueError()
            pages.append(page.extract_text() or "")
            if sum(map(len, pages)) > 200_000:
                raise ValueError()
        print(json.dumps({"pages": pages}))
    except Exception:
        print(
            json.dumps(
                {
                    "error": "Use a readable, unencrypted PDF with at most 100 pages and 200,000 characters."
                }
            )
        )


if __name__ == "__main__":
    main()
