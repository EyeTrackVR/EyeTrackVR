(() => {
  let btn = document.querySelectorAll(".bp");
  btn.forEach((header) => {
    header.addEventListener("click", function (event) {
      console.log(event.target.id);
      document.querySelectorAll(".bpdata").forEach((data) => {
        data.classList.remove("open");
      });
      document.querySelectorAll(".bp").forEach((data) => {
        data.classList.remove("open");
      });
      document
        .querySelector("#" + event.target.id + "_data")
        .classList.add("open");
      document.querySelector("#" + event.target.id).classList.add("open");
      document.querySelector("#bpImage").src =
        "../assets/img/" + event.target.id + ".png";
    });
  });
})();
