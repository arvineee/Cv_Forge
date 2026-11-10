/** Build: npx tailwindcss@3.4.17 -c tailwind.config.js -i tailwind.input.css -o app/static/css/tw.css --minify */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
    "./app/**/*.py",
  ],
  theme: { extend: {} },
  plugins: [],
};
