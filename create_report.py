from datetime import datetime
from pathlib import Path
import re
import subprocess

import reportlab
import yaml
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# =============================================================================
# Settings and input
# =============================================================================
main_path = Path(__file__).resolve().parent
script_path = main_path / "igv_script.txt"
igv_path = "igv"

with (main_path / "input.yaml").open(encoding="utf-8") as file:
    config = yaml.safe_load(file)

samples = config["samples"]
controls = config.get("controls") or []

regions = [
    region.strip()
    for region in config["regions"].split(",")
    if region.strip()
]

max_panel_height = config.get("maxPanelHeight", 1000)

if not samples or not regions:
    raise ValueError("Specify at least one sample and one region")

if type(max_panel_height) is not int or max_panel_height <= 0:
    raise ValueError("maxPanelHeight must be a positive integer")

# Use a new directory for every run to avoid mixing old and new images.
run_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
snapshots_dir = main_path / "snapshots" / run_name
snapshots_dir.mkdir(parents=True, exist_ok=False)

pdf_path = snapshots_dir / "regions.pdf"


# =============================================================================
# Build the IGV script
# =============================================================================
commands = []
screenshots = []

for sample_number, sample in enumerate(samples, start=1):
    sample_name = str(sample["name"])

    # Remove previous tracks before loading the next sample.
    commands.append("new")

    if config.get("genome"):
        commands.append(f'genome {config["genome"]}')

    commands.extend([
        f'snapshotDirectory "{snapshots_dir}"',
        f"maxPanelHeight {max_panel_height}",
        "preference FLANKING_REGION 1000",
        "preference SAM.SHADE_ALIGNMENT_BY MAPPING_QUALITY_HIGH",
        "preference SAM.QUICK_CONSENSUS_MODE true",
    ])

    # Load only this sample and the shared controls.
    for track in [sample] + controls:
        commands.append(f'load "{sample["bam"]}" name="{sample["name"]}"')

    commands.extend([
        "viewaspairs",
        "group REFERENCE_CONCORDANCE",
        "colorBy UNEXPECTED_PAIR",
        "squish",
        'collapse "Refseq All"',
    ])

    for region_number, region in enumerate(regions, start=1):
        # Make a filename safe for both gene names and genomic coordinates.
        label = re.sub(
            r"[^\w.-]+",
            "_",
            f"{sample_name}_{region}",
        )[:150]

        filename = f"{sample_number:03d}_{region_number:03d}_{label}.png"
        image_path = snapshots_dir / filename

        screenshots.append((sample_name, region, image_path))

        commands.extend([
            f"goto {region}",
            f'snapshot "{filename}"',
        ])

commands.append("exit")

script_path.write_text(
    "\n".join(commands) + "\n",
    encoding="utf-8",
)


# =============================================================================
# Run IGV
# =============================================================================
print(
    f"Running IGV: {len(samples)} samples, "
    f"{len(screenshots)} screenshots..."
)

subprocess.run(
    [igv_path, "-b", str(script_path)],
    cwd=main_path,
    check=True,
)

for sample_name, region, image_path in screenshots:
    if not image_path.is_file():
        raise FileNotFoundError(
            f"Missing screenshot: {sample_name}, {region}: {image_path}"
        )


# =============================================================================
# Label PNG images and combine them into one PDF
# =============================================================================
print("Adding image labels and creating PDF...")

# Use a font included with ReportLab.
font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
font = ImageFont.truetype(str(font_path), 24)

pdf = canvas.Canvas(str(pdf_path))
pdf.setTitle("IGV report")

margin = 20
heading_height = 90

for sample_name, region, image_path in screenshots:
    title_lines = [
        f"Sample: {sample_name}",
        f"Region: {region}",
    ]

    with Image.open(image_path) as original:
        # Add space above the image without resizing the original plot.
        text_width = max(font.getbbox(line)[2] for line in title_lines)
        width = max(original.width, text_width + 40)

        image = Image.new(
            "RGB",
            (width, original.height + heading_height),
            "white",
        )
        image.paste(original, (0, heading_height))

    draw = ImageDraw.Draw(image)

    for number, line in enumerate(title_lines):
        draw.text(
            (20, 10 + number * 35),
            line,
            font=font,
            fill="black",
        )

    image.save(image_path)

    # Embed the labelled PNG without reducing its resolution.
    width, height = image.size

    pdf.setPageSize((
        width + 2 * margin,
        height + 2 * margin,
    ))

    pdf.drawImage(
        ImageReader(image),
        margin,
        margin,
        width=width,
        height=height,
    )

    pdf.showPage()
    image.close()

pdf.save()

print(f"PNG directory: {snapshots_dir}")
print(f"PDF saved: {pdf_path}")