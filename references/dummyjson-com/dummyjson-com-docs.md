# DummyJSON - Docs

svg icon

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

DummyJSON can be used with any type of front end project that needs products, carts, users, todos or any dummy data in JSON format.
You can use examples below to check how DummyJSON works.

Feel free to enjoy it in your awesome projects!

[Test Route](#intro-test)

See if your internet is working 😉

```
// Could be GET or POST/PUT/PATCH/DELETE
          fetch('https://dummyjson.com/test')
          .then(res => res.json())
          .then(console.log);

          /* { status: 'ok', method: 'GET' } */
```

[Limiting Resources](#intro-limit)

All the resources can be used with query params to achieve pagination and get limited data. `limit=0` clears the limit and you get all items

```
fetch('https://dummyjson.com/RESOURCE/?limit=10&skip=5&select=key1,key2,key3');
```

It can be comma separated, OR, you can use multiple select query params to get multiple keys.

```
fetch('https://dummyjson.com/RESOURCE/?limit=10&skip=5&select=key1&select=key2&select=key3');
```

[Delay Responses](#intro-delay)

You can simulate a delay in responses using the delay param, delay can be any number between 0 and 5000 milliseconds

```
fetch('https://dummyjson.com/RESOURCE/?delay=1000');
```

[Authorizing Resources](#intro-auth)

All resources can be accessed via an access token to test as a logged-in user.

Go to auth module and generate an auth access token to get data as an authorized user

```
/* providing access token in bearer */
          fetch('https://dummyjson.com/auth/RESOURCE', {
            method: 'GET', /* or POST/PUT/PATCH/DELETE */
            headers: {
              'Authorization': 'Bearer /* YOUR_ACCESS_TOKEN_HERE */', 
              'Content-Type': 'application/json'
            }, 
          })
          .then(res => res.json())
          .then(console.log);
```

[IP Address](#intro-ip)

Get the IP address of the client.

```
// GET
          fetch('https://dummyjson.com/ip')
          .then(res => res.json())
          .then(console.log);

          /* { ip: '127.0.0.1', userAgent: 'Mozilla/5.0 ...' } */
```

[Buy me a coffee](https://buymeacoffee.com/muhammadovi)

Coffee Icon

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->

Github

<!-- 🖼️❌ Image not available. Please use `PdfPipelineOptions(generate_picture_images=True)` -->