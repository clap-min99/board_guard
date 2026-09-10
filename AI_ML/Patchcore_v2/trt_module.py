"""
trt_module.py

TensorRT 10.x 엔진을 로드해서 프레임 단위로 추론하는 래퍼.
anomalib PatchCore/EfficientAD ONNX export는 output이 여러 개
(pred_score, pred_label, anomaly_map, pred_mask 등)라서,
output을 하나만 가정하지 않고 전부 dict로 리턴한다.

PyCUDA 대신 PyTorch 텐서로 GPU 메모리를 관리함 (NVIDIA 공식 권장 방식).
같은 프로세스 안에서 PyTorch(resnet18 등)를 같이 쓸 때, PyCUDA가 별도
CUDA 컨텍스트를 만들면서 생기는 "invalid resource handle" 충돌을 피하기 위함.
"""

import numpy as np
import tensorrt as trt
import torch

_TRT_TO_TORCH_DTYPE = {
    trt.float32: torch.float32,
    trt.float16: torch.float16,
    trt.int8: torch.int8,
    trt.int32: torch.int32,
    trt.bool: torch.bool,
}


class TRTInferenceEngine:
    def __init__(self, engine_path: str):
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.device = torch.device("cuda")

        with open(engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.context = self.engine.create_execution_context()

        self.tensors = {}
        self.input_names = []
        self.output_names = []

        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.context.get_tensor_shape(name))
            trt_dtype = self.engine.get_tensor_dtype(name)
            torch_dtype = _TRT_TO_TORCH_DTYPE.get(trt_dtype, torch.float32)
            mode = self.engine.get_tensor_mode(name)

            # PyTorch가 GPU 메모리를 직접 할당하고, 그 주소를 TensorRT에 알려줌
            tensor = torch.zeros(shape, dtype=torch_dtype, device=self.device)
            self.context.set_tensor_address(name, tensor.data_ptr())

            self.tensors[name] = {"tensor": tensor, "shape": shape, "dtype": torch_dtype}

            if mode == trt.TensorIOMode.INPUT:
                self.input_names.append(name)
            else:
                self.output_names.append(name)

        if len(self.input_names) != 1:
            raise RuntimeError(f"입력이 1개가 아님: {self.input_names}")

        self.input_name = self.input_names[0]

        print("[TRT] 입력:", self.input_name, self.tensors[self.input_name]["shape"])
        print("[TRT] 출력:", self.output_names)

    def infer(self, input_data: np.ndarray) -> dict:
        """
        input_data: (1, 3, H, W) float32
        반환: {output_name: np.ndarray, ...} 형태의 dict
        """
        input_info = self.tensors[self.input_name]
        src = torch.from_numpy(input_data).to(dtype=input_info["dtype"], device=self.device)
        input_info["tensor"].copy_(src)

        stream = torch.cuda.current_stream()
        self.context.execute_async_v3(stream_handle=stream.cuda_stream)
        stream.synchronize()

        results = {}
        for name in self.output_names:
            info = self.tensors[name]
            results[name] = info["tensor"].detach().cpu().numpy().copy()

        return results