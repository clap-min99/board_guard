"""
embedding_utils.py

ImageNet 사전학습 resnet18로 이미지 임베딩(512차원 벡터)을 뽑는 공용 유틸.
build_reference_embeddings.py, classify_by_embedding.py가 공용으로 import해서 씀.

학습을 새로 하지 않음 - resnet18을 "이미지를 벡터로 바꿔주는 도구"로만 사용.
"""

import cv2
import numpy as np
import torch
import torchvision.transforms as T
from torchvision.models import resnet18, ResNet18_Weights

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

_TRANSFORM = T.Compose([
    T.ToPILImage(),
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def load_embedding_model():
    """ImageNet 사전학습 resnet18에서 마지막 분류층(1000class)을 제거해
    512차원 임베딩만 뽑는 추출기로 사용."""
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = torch.nn.Identity()
    model.eval()
    model.to(DEVICE)
    return model


@torch.no_grad()
def get_embedding(model, image_bgr: np.ndarray) -> torch.Tensor:
    """OpenCV BGR 이미지 한 장을 512차원 임베딩 벡터(cpu tensor)로 변환."""
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    tensor = _TRANSFORM(image_rgb).unsqueeze(0).to(DEVICE)
    embedding = model(tensor)
    return embedding.squeeze(0).cpu()


@torch.no_grad()
def get_embeddings_batch(model, images_bgr: list) -> torch.Tensor:
    """여러 장(리스트)을 한 번의 forward pass로 처리 - 조각(patch) 여러 개를
    하나씩 처리하는 것보다 훨씬 빠름. 반환: (N, 512) cpu tensor."""
    tensors = []
    for image_bgr in images_bgr:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        tensors.append(_TRANSFORM(image_rgb))
    batch = torch.stack(tensors).to(DEVICE)
    embeddings = model(batch)
    return embeddings.cpu()