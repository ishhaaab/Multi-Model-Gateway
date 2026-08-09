from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.db import Base
import uuid, datetime

# lifecycle: queued then running to complete or failed or cancelled
TRAINING_STATUSES = {"queued", "running", "complete", "failed", "cancelled"}
TRAINING_STAGES = {"queued", "preparing", "training", "saving", "done"}
# supported base models for fine-tuning
TRAINING_BASE_MODELS = {"flux-dev", "sdxl"}


class TrainingJob(Base):
    """A user fine-tuning job (dataset upload + produced .safetensors artifact).

    Dataset files live under the shared training_data volume at
    {TRAINING_ROOT}/{job_id}/dataset; the produced artifact is stored as
    {TRAINING_ROOT}/{job_id}/{artifact_filename}. Rows are created by the
    upload endpoint (status queued) and updated by the trainer worker as it
    progresses; progress is a 0-100 percent estimate.
    """
    __tablename__ = "trainings"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    base_model = Column(String(32), nullable=False)   # "flux-dev" | "sdxl"
    dataset_dir = Column(String(512), nullable=True)  # path inside the training_data volume
    artifact_filename = Column(String(512), nullable=True)  # produced .safetensors basename
    status = Column(String(16), nullable=False, default="queued")  # queued|running|complete|failed|cancelled
    stage = Column(String(32), nullable=True)  # preparing|training|saving|done
    progress = Column(Integer, nullable=False, default=0)  # 0-100
    params = Column(JSONB, nullable=True)  # dict: steps, learning_rate, etc.
    error = Column(Text, nullable=True)
    sample_image = Column(String(512), nullable=True)  # path to a sample output image
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
