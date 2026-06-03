#!/usr/bin/env python3
import json
import pathlib
try:
    import segno
except ImportError:
    segno = None

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
TRACKS_JSON = ROOT_DIR / "bootc_installer" / "data" / "tracks.json"
OUTPUT_DIR = ROOT_DIR / "bootc_installer" / "assets" / "qr"

def main():
    if segno is None:
        # Check if assets already exist
        all_exist = True
        try:
            with open(TRACKS_JSON, "r", encoding="utf-8") as f:
                tracks = json.load(f)
            for track in tracks:
                qr_asset = track.get("qr_asset")
                if qr_asset and not (OUTPUT_DIR / qr_asset).exists():
                    all_exist = False
                    break
        except Exception:
            all_exist = False

        if all_exist:
            print("WARNING: 'segno' Python library is not installed. Using pre-existing QR SVG assets.")
            return
        else:
            print("ERROR: 'segno' Python library is required to generate missing QR SVG assets. Please run 'pip install segno'.")
            exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACKS_JSON, "r", encoding="utf-8") as f:
        tracks = json.load(f)
    
    for track in tracks:
        url = track.get("url")
        qr_asset = track.get("qr_asset")
        if not url or not qr_asset:
            continue
        
        # Generate QR Code SVG using segno
        qr = segno.make_qr(url)
        output_path = OUTPUT_DIR / qr_asset
        
        # Save SVG with identical options to match our visual design
        qr.save(
            output_path,
            scale=6,
            dark="white",
            light="#1e1e2e"
        )
        print(f"Generated QR Code for '{track.get('title')}' -> {output_path.name}")

if __name__ == "__main__":
    main()
