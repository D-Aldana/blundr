# Blundr knight icon pack

The stumbling-knight mark and the web asset set generated from it.

## Master art

- `source/blundr-knight-master.png`: full-resolution, transparent, flat-color master.
- `source/blundr-knight-transparent-1024.png`: normalized 1024 px transparent source.

Everything else is derived from these two files — regenerate rather than edit.

## Generated assets

The generated set is installed in [`frontend/public/`](../../frontend/public),
which Vite copies to the site root:

- `favicon.ico`: multi-resolution favicon (16, 32, 48, 64, 128, 256 px).
- `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`, `favicon-256x256.png`: explicit browser favicon sizes.
- `apple-touch-icon.png`: 180 px iOS home-screen icon.
- `android-chrome-192x192.png`, `android-chrome-512x512.png`: standard PWA icons.
- `maskable-icon-192x192.png`, `maskable-icon-512x512.png`: extra-padded Android maskable icons.
- `mstile-150x150.png`: Microsoft tile icon.
- `icon-transparent-512x512.png`: transparent mark for product UI and marketing layouts.
- `og-image.png`: 1200 by 630 px social preview image.
- `site.webmanifest`: web app manifest.
- `browserconfig.xml`: Microsoft tile configuration.

## Install elsewhere

To reuse the pack in another app, copy those files to its public or static
root and add this inside the document `<head>`:

```html
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#EEF0EA">
<meta name="msapplication-config" content="/browserconfig.xml">
<meta property="og:image" content="/og-image.png">
<meta name="twitter:card" content="summary_large_image">
```

If the app is hosted below a subpath, update the leading `/` paths in the HTML,
manifest, and browser configuration.

## Brand colors

- Ink navy: `#10214A`
- Paper cream: `#EEF0EA`
- Chalk white: `#FBFCFA`
- Blunder red: `#C8362B`
