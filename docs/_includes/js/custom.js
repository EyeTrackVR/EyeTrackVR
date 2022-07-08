async function switchScheme() {
    localStorage.getItem('theme') === 'dark' ? jtd.setTheme("eyetrackvr") : jtd.setTheme("light");
}
window.onload = function () {
    switchScheme();
};