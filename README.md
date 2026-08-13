# Songs

A public library of piano song data. Each song points to a MusicXML file plus optional
thumbnail and full-size images. A local helper script turns a MusicXML file into a
`songs.json` entry and pushes the change to GitHub.

## Repository structure

```
Songs/
├── songs.json      # the data — an array of song objects
├── content/        # MusicXML files
├── thumbnails/     # small preview images
├── images/         # larger / full images
├── scripts/        # LOCAL helper script (gitignored, not on GitHub)
└── README.md
```

## The schema

`songs.json` is a plain JSON array of objects:

```json
[
  {
    "title": "Happy Birthday",
    "artist": "Mildred J. Hill & Patty Hill",
    "content": "content/happy_birthday.musicxml",
    "thumbnail": "thumbnails/happy_birthday.png",
    "image": "images/happy_birthday.png"
  }
]
```

| Field       | Description                                          |
|-------------|------------------------------------------------------|
| `title`     | Song name                                            |
| `artist`    | Singer or composer                                   |
| `content`   | Path to the MusicXML file (inside `content/`)        |
| `thumbnail` | Path to a small preview image (inside `thumbnails/`) |
| `image`     | Path to a larger image (inside `images/`)            |

All paths are relative to the repo root. If you skip a thumbnail or image, the field is
stored as an empty string `""`.

## How to add a song

Run the helper script with the path to your MusicXML file (you can drag & drop it into
the terminal):

```bash
python3 scripts/add_song.py ~/Downloads/my_song.musicxml
```

The script asks for:

1. **Title** — defaults to a cleaned-up version of the filename
2. **Artist** — singer or composer
3. **Thumbnail path** (optional) — drag & drop an image, or press Enter to skip
4. **Image path** (optional) — drag & drop an image, or press Enter to skip

It then:

1. Copies the MusicXML into `content/`
2. Copies the thumbnail/image into `thumbnails/` / `images/`
3. Adds or updates the entry in `songs.json` (sorted by title)
4. Commits and pushes to GitHub

### Non-interactive mode

You can supply everything up front and skip the questions:

```bash
python3 scripts/add_song.py ~/Downloads/my_song.musicxml \
    --title "My Song" \
    --artist "Some Artist" \
    --thumbnail ~/Downloads/thumb.png \
    --image ~/Downloads/full.png
```

To commit locally without pushing, add `--no-push`.

## First-time setup

Create the repo on GitHub, then link it locally:

```bash
cd Songs
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/Songs.git
git push -u origin main
```

After that, `python3 scripts/add_song.py <file.musicxml>` commits and pushes automatically.

## Why is `scripts/` gitignored?

`add_song.py` is a personal utility — it doesn't belong in a public repo — so it's listed
in `.gitignore`. It still runs locally and does the git commit/push for you.

## Requirements

- Python 3 (built into macOS)
- `git` on your PATH
