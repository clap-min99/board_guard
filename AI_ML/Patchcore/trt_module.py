"""
trt_module.py

TensorRT 10.x 엔진을 로드해서 프레임 단위로 추론하는 래퍼.
anomalib PatchCore/EfficientAD ONNX export는 output이 여러 개
(pred_score, pred_label, anomaly_map, pred_mask 등)라서,
output을 하나만 가정하지 않고 전부 dict로 리턴한다.
"""

import numpy as np
import tensorrt as trt
import pycuda.driver as cuda


class TRTInferenceEngine:
    def __init__(self, engine_path: str):
        self.logger = trt.Logger(trt.Logger.WARNING)

        with open(engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

        self.tensors = {}
        self.input_names = []
        self.output_names = []

        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = self.context.get_tensor_shape(name)
            size = max(trt.volume(shape), 1)
            dtype = trt.nptype(self.engine.get_tensor_dtype(name))
            mode = self.engine.get_tensor_mode(name)

            host_mem = cuda.pagelocked_empty(
                size, dtype, mem_flags=cuda.host_alloc_flags.DEVICEMAP
            )
            device_ptr = host_mem.base.get_device_pointer()
            self.context.set_tensor_address(name, int(device_ptr))

            self.tensors[name] = {"host": host_mem, "shape": tuple(shape), "dtype": dtype}

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
        np.copyto(input_info["host"].reshape(input_info["shape"]), input_data)

        self.context.execute_async_v3(stream_handle=self.stream.handle)
        self.stream.synchronize()

        results = {}
        for name in self.output_names:
            info = self.tensors[name]
            results[name] = info["host"].reshape(info["shape"]).copy()

        return results