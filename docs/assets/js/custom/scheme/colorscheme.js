
/* Legacy function */
const switch_scheme = document.getElementById("switch-mode");
var isClicked = false;
async function toggleDetect() {
  if (isClicked == false) {
    isClicked = true;
    createCookie("isClicked", true, 365);
    switch_scheme.textContent = "Light Mode";
  } else {
    isClicked = false;
    createCookie("isClicked", false, 365);
    switch_scheme.textContent = "Dark Mode";
  }
}

/* Browser detection of color scheme to change the discord widget */
var url = window.location.pathname;

if (
  window.matchMedia("(prefers-color-scheme: light)") &&
  url == "/EyeTrackVR/contact/"
) {
  var discord_scheme = "light";

  document.getElementById("discord-widget").src =
    "https://discord.com/widget?id=946212245187199026&theme=" + discord_scheme;
}

if (
  window.matchMedia("(prefers-color-scheme: dark)") &&
  url == "/EyeTrackVR/contact/"
) {
  var discord_scheme = "dark";

  document.getElementById("discord-widget").src =
    "https://discord.com/widget?id=946212245187199026&theme=" + discord_scheme;
}
