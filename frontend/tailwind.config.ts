import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";
import typography from "@tailwindcss/typography";

const config = {
  plugins: [
    tailwindcssAnimate,
    typography,
  ],
} satisfies Config;

export default config;