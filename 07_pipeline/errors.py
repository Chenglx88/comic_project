"""流水线错误类型。退出码：4 输入/配置缺失，5 校验重试耗尽。"""

from __future__ import annotations


class PipelineError(Exception):
    def __init__(self, message: str, code: int = 5):
        super().__init__(message)
        self.code = code
        self.message = message
