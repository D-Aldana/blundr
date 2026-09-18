# Blundr knight icon pack

Production-ready web assets based on the selected stumbling knight concept.

## Folder contents

- `source/blundr-knight-master.png`: full-resolution, transparent, flat-color master.
- `source/blundr-knight-transparent-1024.png`: normalized 1024 px transparent source.
- `public/favicon.ico`: multi-resolution favicon containing 16, 32, 48, 64, 128, and 256 px variants.
- `public/favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`: explicit browser favicon sizes.
- `public/apple-touch-icon.png`: 180 px iOS home-screen icon.
- `public/android-chrome-192x192.png`, `android-chrome-512x512.png`: standard PWA icons.
- `public/maskable-icon-192x192.png`, `maskable-icon-512x512.png`: extra-padded Android maskable icons.
- `public/mstile-150x150.png`: Microsoft tile icon.
- `public/icon-transparent-512x512.png`: transparent mark for product UI and marketing layouts.
- `public/og-image.png`: 1200 by 630 px social preview image.
- `site.webmanifest`: ready-to-use web app manifest.
- `browserconfig.xml`: Microsoft tile configuration.

## Install

Copy everything inside `public/` to your app's public or static root. Copy `site.webmanifest` and `browserconfig.xml` there too.

Add this inside your document `<head>`:

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

If your app is hosted below a subpath, update the leading `/` paths in the HTML, manifest, and browser configuration.

## Brand colors

- Ink navy: `#10214A`
- Paper cream: `#EEF0EA`
- Chalk white: `#FBFCFA`
- Blunder red: `#C8362B`
