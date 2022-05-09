(() => {
  const chips = {
    d1: {
      width: 1722,
      height: 1552,
      base: "d1_Base.png",
      options: [
        [
          "imu",
          (imu) => (imu == "bno" ? "d1_BNO-Main.png" : "d1_MPU-Main.png"),
        ],
        [
          "aux",
          () => {
            const box = document.querySelector("input[name='d1-imu']:checked");
            return box && box.value == "bno"
              ? "d1_BNO-Aux.png"
              : "d1_MPU-Aux.png";
          },
        ],
        ["battery-sense", () => "d1_Battery-Sense.png"],
        ["charge-diodes", () => "d1_Charge-Diodes.png"],
      ],
    },
  };

  Object.entries(chips).forEach(([chip, config]) => {
    const div = document.getElementById(chip);
    div.style.paddingTop = (config.height / config.width) * 100 + "%";
  });

  const bgGen = () => {
    Object.entries(chips).forEach(([chip, config]) => {
      const bgs = [config.base];
      config.options.forEach(([optName, optVal]) => {
        const box = document.querySelector(
          'input[name="' + chip + "-" + optName + '"]:checked'
        );
        if (box) {
          bgs.push(optVal(box.value));
        }
      });
      const div = document.getElementById(chip);
      div.style.background = bgs
        .map((bg) => "url(../assets/img/" + bg + ") 0 0/100% 100%")
        .reverse()
        .join(",");
    });
  };
  bgGen();
  document.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", bgGen);
  });
})();
