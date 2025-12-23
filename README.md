# FinalBurn Neo [Libretro] Game Launcher

A PyQt6-based GUI launcher for FinalBurn Neo (Libretro core), supporting many retro systems, ROM metadata, and images.

## Features

- **Multi-system support:** Manage and launch ROMs for Arcade, NES, SNES, Sega, Neo-Geo, MSX, ZX Spectrum, and many more.
- **Automatic ROM metadata:** Auto-generate ROM title lists with year and manufacturer info via XML/DAT files.
- **Joystick navigation:** Full joystick/gamepad navigation and controls, including rapid scrolling and system switching.
- **Configurable:** All settings (paths, controls, XML files) are easily editable in the GUI.
- **Fast search & filtering:** Find ROMs quickly by title, year, or manufacturer.
- **Support for Title and Preview Images with automatic prefixing**
- **Cross-platform:** Works on Windows, Linux, and macOS (requires Python 3, PyQt6, and pygame).

## Image Support

For each ROM, the launcher can display **title and preview images**.  
To work, place your images in the designated folders and use the correct filename prefix as specified below.

### Image Naming Convention

- Images must be PNG files.
- The filename format is:  
  `<prefix><rombasename>.png`
- Example: For the NES ROM `mariobros.zip`, the image file would be `nes_mariobros.png`.

### Image Prefixes by System

| System Name                                | Prefix         |
|---------------------------------------------|---------------|
| CBS ColecoVision                           | `cv_`         |
| Fairchild ChannelF                         | `chf_`        |
| MSX 1                                      | `msx_`        |
| Nec PC-Engine                              | `pce_`        |
| Nec SuperGrafX                             | `sgx_`        |
| Nec TurboGrafx-16                          | `tg_`         |
| Nintendo Entertainment System              | `nes_`        |
| Nintendo Family Disk System                | `fds_`        |
| Super Nintendo Entertainment System        | `snes_`       |
| Sega GameGear                              | `gg_`         |
| Sega Master System                         | `sms_`        |
| Sega Megadrive                             | `md_`         |
| Sega SG-1000                               | `sg1k_`       |
| SNK Neo-Geo Pocket                         | `ngp_`        |
| ZX Spectrum                                | `spec_`       |
| Arcade, SNK Neo-Geo CD, and others         | *(no prefix)* |

## Installation

1. **Clone/download** this repository.
2. Install dependencies:
   ```bash
   pip install pyqt6 pygame
   ```
3. Make sure you have [RetroArch](https://www.retroarch.com/) and the FinalBurn Neo core (`fbneo_libretro`).
4. Place your ROMs in the appropriate folders for each system.

---

## Usage

Run the script:
```bash
python fbneo_libretro.py
```

- Set up paths to RetroArch, the FBNeo core, and your ROM folders via the **Settings** dialog.
- Add XML/DAT files for richer ROM metadata.
- Browse, search, and filter your ROMs by system, title, year, or manufacturer.
- Double-click or press your joystick "select" button to launch a game instantly.

---

## Supported Systems

- Arcade
- CBS ColecoVision
- Fairchild ChannelF
- MSX 1
- Nec PC-Engine / SuperGrafX / TurboGrafx-16
- Nintendo Entertainment System (NES) / Famicom Disk System
- Super Nintendo
- Sega GameGear / Master System / Megadrive / SG-1000
- SNK Neo-Geo Pocket / Neo-Geo CD
- ZX Spectrum

---

## Configuration

All settings are stored in `config.json` (auto-generated).  
You can configure:

- Set the directories for ROMs, Title Images, and Preview Images for each system in the **Settings** dialog.
- Paths to RetroArch and FBNeo core (.dll/.so/.dylib)
- ROM folders per system
- XML/DAT metadata files per system (optional)
- Joystick button mappings and scrolling behavior
- If no image is available, the launcher will display `"image not available"` in place of the image.

For SNK Neo-Geo CD specific systems, filenames are used as titles.

---

## Dependencies

- Python 3.6+
- [PyQt6](https://pypi.org/project/PyQt5/)
- [pygame](https://pypi.org/project/pygame/)

---

## Screenshots

![main](https://github.com/gegecom83/fbneo_libretro.py/blob/main/data/main.png)
![settings](https://github.com/gegecom83/fbneo_libretro.py/blob/main/data/settings.png) 


---

## Credits

- Built and maintained by [gegecom83](https://github.com/gegecom83)
- Powered by [FinalBurn Neo](https://github.com/finalburnneo/FBNeo) and [RetroArch](https://www.retroarch.com/)

---

## License

This project is distributed under the MIT License.

---

**Enjoy your retro gaming!**
