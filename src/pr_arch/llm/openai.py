"""OpenAI client. Used only for embeddings."""
from openai import OpenAI
from dotenv import load_dotenv
import httpx
import os

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
API_KEY = os.getenv("OPENAI_API_KEY", "")
_ssl_verify = os.environ.get("OPENAI_SSL_VERIFY", "1").lower() not in ("0", "false", "no")


class OpenAIEmbeddingClient:
    """Thin wrapper around OpenAI's embeddings endpoint."""

    def __init__(self, api_key: str = API_KEY) -> None:
        self._client = OpenAI(
            api_key=api_key,
            http_client=httpx.Client(verify=_ssl_verify),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input, in order."""
        if not texts:
            return []
        resp = self._client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [item.embedding for item in resp.data]