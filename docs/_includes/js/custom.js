async function switchScheme(isClicked) {
  if (isClicked == true) {
    jtd.setTheme("eyetrackvr");
    switch_scheme.textContent = "Light Mode";
  } else {
    jtd.setTheme("light");
    switch_scheme.textContent = "Dark Mode";
  }
}
