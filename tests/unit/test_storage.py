import tempfile

import pytest

from app.core.storage.local import LocalStorage, SecurityError
from app.errors import NotFoundException


@pytest.mark.asyncio
async def test_local_storage_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorage(base_path=tmpdir)
        key = "user_123/doc_456.pdf"
        data = b"%PDF-1.4 test content stream"

        # 1. Save
        saved_key = await storage.save(key, data)
        assert saved_key == key
        assert await storage.exists(key) is True

        # 2. Get bytes
        retrieved = await storage.get_bytes(key)
        assert retrieved == data

        # 3. Get stream
        chunks = []
        async for chunk in storage.get_stream(key, chunk_size=8):
            chunks.append(chunk)
        assert b"".join(chunks) == data

        # 4. Delete
        assert await storage.delete(key) is True
        assert await storage.exists(key) is False

        # 5. Get non-existent raises NotFoundException
        with pytest.raises(NotFoundException):
            await storage.get_bytes(key)


@pytest.mark.asyncio
async def test_local_storage_path_traversal_prevention() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorage(base_path=tmpdir)
        malicious_key = "../../etc/passwd"

        with pytest.raises(SecurityError) as exc_info:
            await storage.save(malicious_key, b"evil")
        assert "path traversal" in str(exc_info.value).lower()
