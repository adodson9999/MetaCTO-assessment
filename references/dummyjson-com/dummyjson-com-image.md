# Image - Docs

svg icon

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

The **image** endpoint provides customizable placeholder images by specifying size in the URL, with options for background color, text color, and display text, ideal for use in websites and wireframes.

The base URL is: [**dummyjson.com/image**](https://dummyjson.com/image)

[Generate square image](#image-square)

```
// https://dummyjson.com/image/SIZE
          fetch('https://dummyjson.com/image/150')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

150x150

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate custom size image](#image-custom-size)

```
// https://dummyjson.com/image/WIDTHxHEIGHT
          fetch('https://dummyjson.com/image/200x100')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

200x100

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate image with custom text](#image-custom-text)

```
// https://dummyjson.com/image/SIZE/?text=TEXT
          fetch('https://dummyjson.com/image/400x200/008080/ffffff?text=Hello+Peter')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

400x200

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate image with custom colors](#image-custom-color)

```
// https://dummyjson.com/image/SIZE/BACKGROUND/COLOR
          fetch('https://dummyjson.com/image/400x200/282828')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

400x200

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate image with different formats](#image-format)

Supported Formats: [**png**](https://dummyjson.com/image/400x200?type=png) **,** [**jpeg**](https://dummyjson.com/image/400x200?type=jpg) **,** [**webp**](https://dummyjson.com/image/400x200?type=webp)

```
// https://dummyjson.com/image/SIZE/BACKGROUND/COLOR
          fetch('https://dummyjson.com/image/400x200?type=webp&text=I+am+a+webp+image')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/webp'}
```

### Output:

400x200

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate image with custom font family](#image-font-family)

Supported Fonts: [**bitter**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=bitter) **,** [**cairo**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=cairo) **,** [**comfortaa**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=comfortaa) **,** [**cookie**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=cookie) **,** [**dosis**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=dosis) **,** [**gotham**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=gotham) **,** [**lobster**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=lobster) **,** [**marhey**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=marhey) **,** [**pacifico**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=pacifico) **,** [**poppins**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=poppins) **,** [**quicksand**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=quicksand) **,** [**qwigley**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=qwigley) **,** [**satisfy**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=satisfy) **,** [**ubuntu**](https://dummyjson.com/image/250?text=Hello+Peter!&fontFamily=ubuntu)

```
// https://dummyjson.com/image/SIZE/BACKGROUND/COLOR
          fetch('https://dummyjson.com/image/400x200/282828?fontFamily=pacifico&text=I+am+a+pacifico+font')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

400x200

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate image with custom font size](#image-font-size)

```
// https://dummyjson.com/image/SIZE/?text=TEXT&fontSize=FONT_SIZE
          fetch('https://dummyjson.com/image/400x200/008080/ffffff?text=Hello+Peter!&fontSize=16')
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

400x200

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Generate identicon](#image-identicon)

```
// https://dummyjson.com/icon/HASH/SIZE/?type=png (or svg)
          fetch('https://dummyjson.com/icon/abc123/150') // png is default
          .then(response => response.blob()) // Convert response to blob
          .then(blob => {
            console.log('Fetched image blob:', blob);
          })
          // Blob {size: SIZE, type: 'image/png'}
```

### Output:

identicon

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

[Buy me a coffee](https://buymeacoffee.com/muhammadovi)

Coffee Icon

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->