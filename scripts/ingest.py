"""Import local knowledge files into the configured vector store."""

from app.core.config import get_settings
from app.rag.repository import create_vector_repository
from app.rag.service import RagService


def main() -> None:
    settings = get_settings()
    repository = create_vector_repository(settings)
    try:
        service = RagService(settings, repository)
        imported = service.ingest_directory()
        print(f"导入完成：本次 {imported} 个文本块，当前共 {service.count()} 个文本块")
    finally:
        repository.close()


if __name__ == "__main__":
    main()

