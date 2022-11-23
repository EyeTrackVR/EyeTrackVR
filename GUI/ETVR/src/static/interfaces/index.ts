export interface IdropDataData {
  name: string
  icon: JSX.Element
  id: string
}

export interface IgeneralSettings {
  name: string,
  label: string,
  tooltip: string,
  type: string,
}
export interface IalgoSettings {
  name: string,
  id: string,
  min: number,
  max: number,
  value: number,
  step: number,
  tooltip: string,
}

