from DIGEST_APP.CONFIG.config_CLI import parse_args
from DIGEST_APP.APP.dto import RuntimeContext
from DIGEST_APP.CONFIG.config import DigestConfig
from GENERAL.loadconfig import load_config


class GetContext:
    def run(self) -> RuntimeContext:
        args = parse_args()
        config = load_config(args.config, DigestConfig)
        return RuntimeContext(app=config)
