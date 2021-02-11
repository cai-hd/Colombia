from pathlib import Path
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import select_autoescape
from log import logger

TEMPLATES_PATH = Path(__file__).parent / "templates"
OUTPUT_PATH = Path(__file__).parent / "output"


class OutputManager:
    def __init__(self):
        self.output_path = OUTPUT_PATH
        self.written_paths: set = set()
        templates_paths = [str(TEMPLATES_PATH)]
        env = Environment(
            loader=FileSystemLoader(templates_paths),
            autoescape=select_autoescape("html"),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env = env

    def open(self, file_name, mode="w"):
        path = self.output_path / file_name
        self.written_paths.add(path)
        return path.open(mode)

    def exists(self, file_name: str):
        path = self.output_path / file_name
        return path.exists()

    @logger.catch
    def render_template(self, context: dict, output_file_name: str):
        path = self.output_path / "{}.html".format(output_file_name)
        self.written_paths.add(path)
        logger.info(f"Generating {output_file_name}..")
        template = self.env.get_template("{}.html".format(output_file_name))
        template.stream(**context).dump(str(path))


