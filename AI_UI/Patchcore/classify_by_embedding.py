"""
classify_by_embedding.py

PatchCore가 찾은 결함 위치(crop 이미지)를 받아서, build_reference_embeddings.py로
미리 만들어둔 reference_embeddings.pt와 비교해 가장 가까운 불량 유형을 찾는 모듈.

1-NN(최근접 이웃) 방식: 모든 유형의 모든 레퍼런스 벡터 중 거리가 가장 가까운 하나를
찾고, 그 벡터가 속한 유형을 답으로 반환.

단독 실행(테스트용):
    python3 classify_by_embedding.py --image crop_sample.jpg --ref reference_embeddings.pt

다른 코드(pcb_inspector 등)에서 함수로 사용:
    from classify_by_embedding import load_reference, classify_defect_type
    reference, model = load_reference("reference_embeddings.pt")
    type_name, distance = classify_defect_type(crop_bgr, reference, model)
"""

import argparse

import cv2
import torch

from embedding_utils import load_embedding_model, get_embedding


def load_reference(ref_path: str):
    """저장된 레퍼런스 임베딩 + 임베딩 모델을 로드. (reference_dict, model) 반환.
    실전에서는 프로그램 시작할 때 한 번만 호출하고, 그 결과를 계속 재사용해야 함
    (매 프레임마다 다시 로드하면 느려짐)."""
    reference = torch.load(ref_path)
    model = load_embedding_model()
    return reference, model


def classify_defect_type(image_bgr, reference: dict, model, max_distance: float | None = None):
    """
    image_bgr: crop된 결함 이미지 (OpenCV BGR)
    max_distance: 이 값보다 멀면 "아는 유형이 아니다"로 처리 (선택, 처음엔 None으로 시작 추천)
    반환: (type_name, distance) - 모르는 유형으로 처리되면 (None, distance)
    """
    query_emb = get_embedding(model, image_bgr)  # (512,)

    best_type = None
    best_distance = float("inf")

    for type_name, ref_embs in reference.items():
        distances = torch.norm(ref_embs - query_emb.unsqueeze(0), dim=1)
        min_dist = distances.min().item()
        if min_dist < best_distance:
            best_distance = min_dist
            best_type = type_name

    if max_distance is not None and best_distance > max_distance:
        return None, best_distance

    return best_type, best_distance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="분류할 결함 crop 이미지")
    parser.add_argument("--ref", default="reference_embeddings.pt", help="레퍼런스 임베딩 파일")
    parser.add_argument("--max-distance", type=float, default=None,
                         help="이 값보다 멀면 UNKNOWN 처리 (선택)")
    args = parser.parse_args()

    reference, model = load_reference(args.ref)

    img = cv2.imread(args.image)
    if img is None:
        raise RuntimeError(f"이미지를 못 불러옴: {args.image}")

    type_name, distance = classify_defect_type(img, reference, model, args.max_distance)

    print(f"이미지: {args.image}")
    print(f"가장 가까운 유형: {type_name if type_name else 'UNKNOWN'}")
    print(f"거리: {distance:.4f}")


if __name__ == "__main__":
    main()
