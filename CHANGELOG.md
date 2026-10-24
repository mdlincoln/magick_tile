# Changelog

Changes to what `magick_tile` writes: the directory layout of a tree and the
`info.json` payload. Anything that changes either is recorded here, with what a
consumer has to do about it.

## 0.4.0

### Breaking changes

- **`scaleFactors` extend to the whole-image level.** The pyramid's coarsest level
  is derived from the image's longer side, so it is now the level where the whole
  image fits in a single tile — the tier-0 scale of clients that count tiers from
  the image dimensions rather than reading `scaleFactors`. A 2676×1572 image at
  512 px goes from `[1, 2]` to `[1, 2, 4, 8]`. Every image larger than one tile
  gains at least one level, and elongated shapes gain more.

- **The coarsest level is written under both spellings of the whole image.**
  Clients disagree about how to name that level: OpenSeadragon and OpenLayers
  rewrite a whole-image region to the canonical `full` region and request
  `full/{w},{h}/0/`, while leaflet-iiif requests the explicit region
  `0,0,{W},{H}/{w},{h}/0/`. Image API 3.0 §4.4 makes `full` the canonical form,
  so a dynamic server redirects one to the other, but a static tree cannot, so
  both files are written. The `full` copy is not added to `info.json`'s `sizes`,
  which stays the list of aspect-correct thumbnails.

- Regenerate existing trees when upgrading. A tree written by 0.3.0 has a shorter
  level list and neither file, so a client asks for a level that is not there as
  soon as it opens the image.

### Notes

- **2.1 size directories collide for some aspect ratios.** 2.1 addresses a size
  as `{w},`, so the coarsest level can share a directory with a declared
  thumbnail: for 4096×3011 at 512 px the level is 512×377 while the declared size
  512 is 512×376, and both are `full/512,/`. The declared thumbnail keeps its
  declared dimensions and the level's `full` file is not written, because
  overwriting the thumbnail would break the `sizes` contract. The URL still
  resolves, a width-only segment makes no height promise to the client, and the
  explicit-region spelling is still written at the level's own size. 3.0's size
  directories carry the height, so no collision is possible there.

## 0.3.0

### Breaking changes

- `scaleFactors` start at 1, so trees gain a native-resolution level. Viewers
  derive every level from the largest entry and assume the pyramid descends by
  two to native resolution, so a pyramid that started at 2 made them request
  tiles that were never written.
- 3.0 region tiles moved from the `w,` to the canonical `w,h` size directory.

A tree written by 0.2.0 is missing tiles that viewers request; regenerate it.

## 0.2.0

### Breaking changes

- 3.0 trees write canonical `w,h` size directories (previously `w,`) and gain a
  `full/max/0/` full-size image. 2.1 keeps the unscaled image at `full/full/0/`.
- 2.1 payloads changed shape: `@type` is now emitted, and `profile` declares
  `level0` instead of `level1`, widening to a list when formats beyond jpg are
  generated.

Regenerate existing trees when upgrading.

Earlier releases are not reconstructed here; `git log` is the record for them.
