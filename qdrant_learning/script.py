from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

qdrant_url = "http://localhost:6333"
client = QdrantClient(url = qdrant_url)

client.create_collection(
  collection_name="toy_docs",
  vectors_config=VectorParams(size=4, distance=Distance.COSINE)
)

print(client.get_collections())
