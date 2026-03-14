## Create a temp directory for the DaisyUI files
mkdir daisy_setup

cd daisy_setup

## Get Tailwind CSS - https://tailwindcss.com/blog/standalone-cli
curl -sLo ./tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64

chmod +x tailwindcss

## Get DaisyUI
curl -sLo ./daisyui.js https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.js

curl -sLo ./daisyui-theme.js https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.js

## Create input.css file
echo '@import "tailwindcss" source(none);
@plugin "./daisyui.js";
@source "../templates";' >> ./input.css

(adjust relevant paths for your templates)

## Usage with Django
tailwindcss -m -i input.css -o main.css --watch

(adjust relevant paths for input.css and main.css)
