async function switchScheme(isClicked) {
  if (isClicked == true) {
    jtd.setTheme("eyetrackvr");
    var color_scheme = "dark";
  } else {
    jtd.setTheme("light");
    var color_scheme = "light";
  }
  document.getElementById("discord-widget").src =
    "https://discord.com/widget?id=946212245187199026&theme=" + color_scheme;
}