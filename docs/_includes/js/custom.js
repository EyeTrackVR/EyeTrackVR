var isClicked = false;
async function toggleDetect() {
  if (isClicked == false) {
    isClicked = true;
  } else {
    isClicked = false;
  }
  await switchScheme(isClicked);
}

async function switchScheme(isClicked) {
  if (isClicked == true) {
    jtd.setTheme("eyetrackvr");
  } else {
    jtd.setTheme("light");
  }
}
