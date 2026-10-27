import logging


def configure_logging() -> None:
    """配置服务日志。"""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
