# Quick Share icons

`quick-share-logo.png` is an unmodified copy of the supplied blue-and-white logo.
It is used by the sharing target, sharing page and transfer plugin.

`icon-m-quickshare.svg` redraws the two arrow outlines as a clean monochrome
system-settings glyph. Its PNG exports in `theme/` are transparent white masks
at the medium-icon sizes for seven Sailfish display densities. The Silica theme
provider applies the current system icon color. Both current `silica` and legacy
`meegotouch` theme paths are packaged.

To regenerate the PNG exports with Node.js and the development dependency `sharp`:

```sh
node tools/build-icons.cjs
```

The generated PNGs are committed, so building an RPM does not require Node.js.
