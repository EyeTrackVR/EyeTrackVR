(() => {
  const components = [
    {
      name: "Microcontroller",
      choices: [
        {
          name: "Wemos D1 Mini",
          amount: () => 5,
          cost: 1.85,
          costAll: () => 5 * 1.85 + 2.53,
          links:
            '<a href="https://www.aliexpress.com/wholesale?SearchText=D1+mini">Aliexpress Wemos D1 Mini</a>',
        },
      ],
    },
    {
      name: "IMU",
      choices: [
        {
          name: "MPU6050",
          amount: (set) => set,
          cost: 1.38,
          costAll: (set) => set * 1.38 + 1.67,
          links:
            '<a href="https://www.aliexpress.com/wholesale?SearchText=MPU6050">Aliexpress MPU6050</a>',
        },
        {
          name: "BNO085",
          amount: (set) => set,
          cost: 60.0,
          costAll: (set) => set * 60.0 + 1,
          links:
            '<a href="https://www.aliexpress.com/wholesale?SearchText=BNO085">Aliexpress BNO085</a> Please note these boards are both hard to get and may cost up to $80',
        },
      ],
    },
    {
      name: "Batteries",
      choices: [
        {
          name: "3.7v Li-ion polymer 804040",
          amount: () => 5,
          cost: 3.66,
          costAll: () => 5 * 3.19 + 5.33,
          links:
            'This is a rough price, but these are some options: <a href="https://www.aliexpress.com/item/33021202630.html">Batteries, choose 4 pack + 1</a> or <a href="https://www.aliexpress.com/item/1005002559604104.html">pack of 10</a>',
        },
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
      ],
    },
    {
      name: "Charging board",
      choices: [
        {
          name: "TP4056-based USB charging board",
          amount: () => 5,
          cost: 0.34,
          costAll: () => 5 * 0.34 + 1.42,
          links:
            '<a href="https://www.aliexpress.com/item/32649780468.html">Aliexpress TP4056</a>',
        },
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
      ],
    },
    {
      name: "Power switches",
      choices: [
        {
          name: "10 pcs 2 Position",
          amount: () => 1,
          cost: 2.36,
          costAll: () => 2.36,
          links:
            '<a href="https://www.aliexpress.com/item/32975535599.html">Aliexpress 10 pcs 2 Position</a>',
        },
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
      ],
    },
    {
      name: "Wiring for soldering",
      choices: [
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
        {
          name: "24-26 AWG 5m",
          amount: () => 1,
          cost: 1.85,
          costAll: () => 1.85 + 1.68,
          links:
            '<a href="https://www.aliexpress.com/item/1005002632016529.html">aliexpress 22 AWG 5m</a>',
        },
      ],
    },
    {
      name: "Wiring for extensions",
      hideFor5Set: true,
      choices: [
        {
          name: "JST connectors - 5 pin 5 pcs",
          amount: () => 1,
          cost: 1.55,
          costAll: () => 1.55,
          links:
            '<a href="https://www.aliexpress.com/item/1005002304293157.html">Aliexpress JST connectors</a>',
        },
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
      ],
    },
    {
      name: "Cases",
      choices: [
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
        {
          name: "3D printed yourself, approximate $",
          amount: () => 5,
          cost: 2,
          costAll: () => 10,
          links: "You make your own cases!",
        },
        {
          name: "Amazon cases, pack of 6",
          amount: () => 1,
          cost: 7.49,
          costAll: () => 7.49,
          links:
            '<a href="https://www.amazon.com/dp/B08T97JD6Z">Amazon cases</a>. Not guaranteed to fit, measure yourself before ordering.',
        },
      ],
    },
    {
      name: "Straps",
      choices: [
        {
          name: "Sourced elsewhere",
          amount: () => 0,
          cost: 0,
          costAll: () => 0,
          links: "",
        },
        {
          name: "Generic Aliexpress straps",
          amount: () => 2,
          cost: 5,
          costAll: () => 13,
          links:
            '<a href="https://aliexpress.com/item/1005001908740631.html">Aliexpress straps</a>, get some in different sizes?',
        },
      ],
    },
  ];

  const makeElement = (parent, type, contents = "") => {
    let el = document.createElement(type);
    el.innerHTML = contents;
    parent.appendChild(el);
    return el;
  };

  const tbody = document.getElementById("diy-components");

  const updatePrices = () => {
    const set = document.querySelector("input[name=diy-set]:checked").value;
    let total = 0;
    components.forEach((component) => {
      if (component.hideFor5Set) {
        component.tr.style.visibility = set == 5 ? "hidden" : "visible";
        if (set == 5) {
          return;
        }
      }
      const updateValues = (choice) => {
        component.amount.innerHTML = choice.amount(set);
        component.cost.innerHTML = "$" + choice.cost;
        component.costAll.innerHTML =
          "~$" + Math.round(choice.costAll(set) * 100) / 100;
        component.links.innerHTML = choice.links;

        total += choice.costAll(set);
      };
      if (component.choices.length == 1) {
        updateValues(component.choices[0]);
      } else {
        updateValues(component.choices[component.select.value]);
      }
    });

    document.getElementById("diy-total").innerHTML =
      Math.round(total * 100) / 100;
  };

  components.forEach((component) => {
    const tr = makeElement(tbody, "tr");
    component.tr = tr;
    makeElement(tr, "th", component.name);

    const choice = makeElement(tr, "td");
    if (component.choices.length == 1) {
      choice.innerHTML = component.choices[0].name;
    } else {
      const select = makeElement(choice, "select");
      select.name = "name-" + component.name;
      component.choices.forEach((choice, index) => {
        const option = makeElement(select, "option", choice.name);
        option.value = index;
      });
      select.addEventListener("change", updatePrices);
      component.select = select;
    }

    component.amount = makeElement(tr, "td", 0);
    component.cost = makeElement(tr, "td", 0);
    component.costAll = makeElement(tr, "td", 0);
    component.links = makeElement(tr, "td", 69);
  });

  updatePrices();
  document.querySelectorAll('input[name="diy-set"]').forEach((set) => {
    set.addEventListener("change", updatePrices);
  });
})();
