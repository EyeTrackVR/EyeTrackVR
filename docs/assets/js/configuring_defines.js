(() => {
  const types = {
    SELECT: (name, opts, callback) => {
      let select = document.createElement("select");
      Object.entries(opts.values).forEach(([key, value]) => {
        let option = document.createElement("option");
        option.value = key;
        option.innerHTML = value;
        select.appendChild(option);
      });

      callback(Object.keys(opts.values)[0]);
      select.addEventListener("change", (e) => {
        callback(e.target.value);
      });
      return select;
    },
    INPUT: (name, opts, callback) => {
      let input = document.createElement("input");
      input.value = opts.default;
      callback(opts.default);
      input.addEventListener("change", (e) => {
        callback(e.target.value);
      });
      return input;
    },
    CHECKBOX: (name, opts, callback) => {
      let label = document.createElement("label");
      let input = document.createElement("input");
      input.type = "checkbox";
      if (opts.default) {
        input.checked = "checked";
      }
      callback(opts.default);
      input.addEventListener("change", (e) => {
        callback(e.target.checked);
      });

      label.appendChild(input);
      label.appendChild(document.createTextNode(" " + opts.text));
      return label;
    },
    HTML: (name, opts, callback) => {
      let div = document.createElement("div");
      div.innerHTML = opts.html;
      return div;
    },
    ROTATION: (name, opts, callback) => {
      let div = document.createElement("div");
      opts.values.forEach((val) => {
        let label = document.createElement("label");
        let input = document.createElement("input");
        input.type = "radio";
        input.name = "rotation_" + name;
        if (val.default) {
          input.checked = "checked";
          callback(val.value);
        }
        input.addEventListener("change", (e) => {
          callback(e.target.value);
        });
        input.value = val.value;
        label.appendChild(input);

        label.appendChild(document.createTextNode(" " + val.value));
        label.classList.add("rotation");
        div.appendChild(label);
      });
      return div;
    },
  };
  const options = {
    board: {
      name: "Microcontroller",
      renderer: types.SELECT,
      values: {
        WEMOSD1MINI: "Wemos D1 Mini",
        NODEMCU: "NodeMCU",
        TTGO_TBASE: "TTGO TBASE",
        SLIMEVR: "SlimeVR",
        SLIMEVR_DEV: "SlimeVR Dev",
        WROOM32: "WROOM32",
        CUSTOM: "Custom board",
      },
      action: (vals) => {
        if (vals.board == "SLIMEVR" || vals.board == "SLIMEVR_DEV") {
          return {
            board: vals.board,
            sda: "4",
            scl: "5",
            int: "10",
            int_2: "13",
            battery: "17",
          };
        } else if (vals.board == "NODEMCU" || vals.board == "WEMOSD1MINI") {
          return {
            board: vals.board,
            sda: "D2",
            scl: "D1",
            int: "D5",
            int_2: "D6",
            battery: "A0",
          };
        } else if (vals.board == "TTGO_TBASE") {
          return {
            board: vals.board,
            sda: "5",
            scl: "4",
            int: "14",
            int_2: "13",
            battery: "A0",
          };
        } else if (vals.board == "WROOM32") {
          return {
            board: vals.board,
            sda: "21",
            scl: "22",
            int: "23",
            int_2: "25",
            battery: "36",
          };
        } else {
          return { board: vals.board };
        }
      },
    },
    battery: {
      name: "Pin for battery level",
      renderer: types.INPUT,
      default: "A0",
      hidden: (vals) => vals.board != "CUSTOM",
      action: (vals) => {
        return { battery: vals.battery };
      },
    },
    sda: {
      name: "Pin IMU SDA",
      renderer: types.INPUT,
      default: "D2",
      hidden: (vals) => vals.board != "CUSTOM",
      action: (vals) => {
        return { sda: vals.sda };
      },
    },
    scl: {
      name: "Pin IMU SCL",
      renderer: types.INPUT,
      default: "D1",
      hidden: (vals) => vals.board != "CUSTOM",
      action: (vals) => {
        return { scl: vals.scl };
      },
    },
    int: {
      name: "Pin IMU INT",
      renderer: types.INPUT,
      default: "D5",
      hidden: (vals) => vals.board != "CUSTOM",
      action: (vals) => {
        return { int: vals.int };
      },
    },
    int_2: {
      name: "Pin IMU INT_2",
      renderer: types.INPUT,
      default: "D6",
      hidden: (vals) => vals.board != "CUSTOM",
      action: (vals) => {
        return { int_2: vals.int_2 };
      },
    },
    imu: {
      name: "Sensor",
      renderer: types.SELECT,
      values: {
        IMU_BNO085: "BNO085",
        IMU_BNO080: "BNO080",
        IMU_BNO055: "BNO055",
        IMU_MPU9250: "MPU9250",
        IMU_MPU6500: "MPU6500",
        IMU_MPU6050: "MPU6050",
      },
      action: (vals) => {
        return { imu: vals.imu };
      },
    },
    mpu9250_warning: {
      name: "",
      renderer: types.HTML,
      html: '<strong style="color: orange;">WARNING: The MPU9250 is not fully supported. You can also try setting is as a MPU6050 or MPU6500 instead if you encounter issues.</strong>',
      hidden: (vals) =>
        !(vals.imu == "IMU_MPU9250" || vals.imu_2 == "IMU_MPU9250"),
      action: () => {
        return {};
      },
    },
    imu_2: {
      name: "Auxiliary sensor",
      renderer: types.SELECT,
      values: {
        IMU_BNO085: "BNO085",
        IMU_BNO080: "BNO080",
        IMU_BNO055: "BNO055",
        IMU_MPU9250: "MPU9250",
        IMU_MPU6500: "MPU6500",
        IMU_MPU6050: "MPU6050",
      },
      action: (vals) => {
        return { imu_2: vals.imu_2 };
      },
    },
    rotation_image: {
      name: "",
      renderer: types.HTML,
      html: '<img src="../assets/img/rotation.png">',
      action: () => {
        return {};
      },
    },
    rotation: {
      name: "IMU rotation",
      renderer: types.ROTATION,
      values: [
        { value: "DEG_270" },
        { value: "DEG_180" },
        { value: "DEG_90", default: true },
        { value: "DEG_0" },
      ],
      action: (vals) => {
        return { rotation: vals.rotation };
      },
    },
    rotation_2: {
      name: "Auxiliary IMU rotation",
      renderer: types.ROTATION,
      values: [
        { value: "DEG_270" },
        { value: "DEG_180" },
        { value: "DEG_90", default: true },
        { value: "DEG_0" },
      ],
      action: (vals) => {
        return { rotation_2: vals.rotation_2 };
      },
    },
    battery_shield: {
      name: "Wemos Battery Shield",
      renderer: types.CHECKBOX,
      text: "I am using the Wemos Battery Shield product",
      default: false,
      hidden: (vals) => !(vals.board == "WEMOSD1MINI"),
      action: (vals) => {
        return { battery_shield: vals.battery_shield };
      },
    },
  };

  const definesCode = document.getElementById("defines_code");
  const button = document.getElementById("defines_download");
  button.download = "defines.h";
  const makeDefine = (vals) => {
    let c = `#define IMU ${vals.imu}
${vals.imu_2 ? "#define SECOND_IMU " + vals.imu_2 : ""}
#define BOARD BOARD_${vals.board}
#define IMU_ROTATION ${vals.rotation}
#define SECOND_IMU_ROTATION ${vals.rotation_2}
// Battery monitoring options (comment to disable):
// BAT_EXTERNAL for ADC pin, BAT_INTERNAL for internal - can detect only low battery, BAT_MCP3021 for external ADC
#define BATTERY_MONITOR BAT_EXTERNAL
#define BATTERY_SHIELD_RESISTANCE ${
      vals.battery_shield ? "130" : "180"
    } //130k BatteryShield, 180k SlimeVR or fill in external resistor value in kOhm
#define PIN_IMU_SDA ${vals.sda}
#define PIN_IMU_SCL ${vals.scl}
#define PIN_IMU_INT ${vals.int}
#define PIN_IMU_INT_2 ${vals.int_2}
#define PIN_BATTERY_LEVEL ${vals.battery}
`;

    definesCode.innerText = c;
    button.href = "data:text/plain;charset=utf-8," + encodeURIComponent(c);
  };

  const values = {};

  const runActions = () => {
    let output = {};
    Object.entries(options).forEach(([option, config]) => {
      const hidden = config.hidden_handler();
      if (!hidden) {
        Object.assign(output, config.action(values));
      }
    });
    makeDefine(output);
  };

  const definesConfig = document.getElementById("defines_config");
  let startup = true;
  Object.entries(options).forEach(([option, config]) => {
    const dt = document.createElement("dt");
    if (config.name) {
      dt.innerHTML = config.name;
      definesConfig.appendChild(dt);
    }
    const dd = document.createElement("dd");

    config.hidden_handler = () => {
      const hidden = config.hidden && config.hidden(values);
      dd.style.display = dt.style.display = hidden ? "none" : "block";
      return hidden;
    };
    config.hidden_handler();

    dd.appendChild(
      config.renderer(option, config, (new_value) => {
        values[option] = new_value;
        if (!startup) {
          runActions();
        }
      })
    );
    definesConfig.appendChild(dd);
  });
  startup = false;
  runActions();
})();
