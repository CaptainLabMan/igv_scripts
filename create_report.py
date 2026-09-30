from pathlib import Path
import subprocess

import yaml
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# =============================================================================
# Settings
# =============================================================================
main_path = Path(__file__).resolve().parent
script_path = main_path / "igv_script.txt"
#igv_path = Path("/path/to/IGV/igv.sh")
igv_path = 'igv'


# =============================================================================
# Read input
# =============================================================================
with (main_path / "input.yaml").open(encoding="utf-8") as file:
    config = yaml.safe_load(file)

samples = config["samples"]
controls = config.get("controls", [])

regions = [
    region.strip()
    for region in config["regions"].split(",")
    if region.strip()
]

if not samples or not regions:
    raise ValueError("Specify at least one sample and one region")

samples_names = "_".join(sample["name"] for sample in samples)

snapshots_dir = main_path / "snapshots" / samples_names
snapshots_dir.mkdir(parents=True, exist_ok=True)

pdf_path = snapshots_dir / "regions.pdf"


# =============================================================================
# Build the IGV script
# =============================================================================
commands = [
    "new",
    f'snapshotDirectory "{snapshots_dir}"',
    "maxPanelHeight 1000",
    "preference FLANKING_REGION 1000",
    "preference SAM.SHADE_ALIGNMENT_BY MAPPING_QUALITY_HIGH",
    "preference SAM.QUICK_CONSENSUS_MODE true",
]

# Select a genome if specified in input.yaml.
if config.get("genome"):
    commands.append(f'genome {config["genome"]}')

# Load all samples and controls into the same session.
for sample in samples + controls:
    commands.append(f'load "{sample["bam"]}"')

commands.extend([
    "viewaspairs",
    "group REFERENCE_CONCORDANCE",
    "colorBy UNEXPECTED_PAIR",
    "squish", # collapse / squish / expand
    'collapse "Refseq All"',
])

# Keep image paths in the same order as the regions.
screenshots = []

for number, region in enumerate(regions, start=1):
    filename = f"{number:03d}_{region.replace(':', '_')}.png"
    image_path = snapshots_dir / filename
    screenshots.append((region, image_path))

    commands.extend([
        f"goto {region}",
        f'snapshot "{filename}"',
    ])

# Close this IGV instance after all snapshots are saved.
commands.append("exit")

script_path.write_text(
    "\n".join(commands) + "\n",
    encoding="utf-8",
)


# =============================================================================
# Run IGV and wait for it to exit
# =============================================================================
print("Running IGV...")

subprocess.run(
    [str(igv_path), "-b", str(script_path)],
    cwd=main_path,
    check=True,
)


# =============================================================================
# Build the PDF
# =============================================================================
print("Creating PDF...")

# Check that all expected screenshots exist.
for region, image_path in screenshots:
    if not image_path.is_file():
        raise FileNotFoundError(f"Missing screenshot for {region}: {image_path}")

pdf = canvas.Canvas(str(pdf_path))
pdf.setTitle(samples_names)

margin = 20
heading_height = 50
scale = 1

for region, image_path in screenshots:
    image = ImageReader(str(image_path))
    width, height = image.getSize()

    width *= scale
    height *= scale

    # Give each image its own page without changing its proportions.
    page_width = width + 2 * margin
    page_height = height + 2 * margin + heading_height

    pdf.setPageSize((page_width, page_height))

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin, page_height - margin - 14, region)

    pdf.drawImage(
        image,
        margin,
        margin,
        width=width,
        height=height,
        mask="auto",
    )

    pdf.showPage()

pdf.save()

print(f"PDF saved: {pdf_path}")