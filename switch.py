"""Support for MyHome switches (light modules, controlled outlets, relays, and heating actuators)."""
from homeassistant.components.switch import (
    DOMAIN as PLATFORM,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)

from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
    OWNHeatingEvent,       # Aggiunta per termoarredo
    OWNHeatingCommand,     # Aggiunta per termoarredo
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_ICON,
    CONF_ICON_ON,
    CONF_WHO,
    CONF_WHERE,
    CONF_BUS_INTERFACE,
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS,
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    devices_to_add = []
    configured_devices = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for device_id, config in configured_devices.items():
        who = config.get(CONF_WHO)
        
        if who == "1": # Switch di illuminazione esistente
            LOGGER.debug(f"Configuring MyHOMESwitch (WHO=1): {device_id} with config {config}")
            instance = MyHOMESwitch(
                hass=hass,
                device_id=device_id,
                who=who,
                where=config[CONF_WHERE],
                icon=config.get(CONF_ICON), # Usare .get() per opzionali
                icon_on=config.get(CONF_ICON_ON),
                interface=config.get(CONF_BUS_INTERFACE),
                name=config[CONF_NAME],
                entity_name=config.get(CONF_ENTITY_NAME),
                device_class=config.get(CONF_DEVICE_CLASS, SwitchDeviceClass.SWITCH), # Default
                manufacturer=config.get(CONF_MANUFACTURER, "BTicino S.p.A."),
                model=config.get(CONF_DEVICE_MODEL, "Lighting Actuator"),
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            devices_to_add.append(instance)
        elif who == "4": # Nuovo switch attuatore per termoarredo
            LOGGER.info(f"Configuring MyHomeActuatorSwitch (WHO=4 - Termoarredo): {device_id} with config {config}")
            instance = MyHomeActuatorSwitch(
                hass=hass,
                device_id=device_id,
                who=who,
                where=config[CONF_WHERE], # Formato atteso: Z#N, es. "9#1"
                name=config[CONF_NAME],
                # I seguenti potrebbero non essere direttamente applicabili o necessitare di valori specifici
                entity_name=config.get(CONF_ENTITY_NAME, config[CONF_NAME]), # Default a nome principale se non specificato
                icon=config.get(CONF_ICON), 
                icon_on=config.get(CONF_ICON_ON),
                device_class=config.get(CONF_DEVICE_CLASS, SwitchDeviceClass.SWITCH),
                manufacturer=config.get(CONF_MANUFACTURER, "BTicino S.p.A."),
                model=config.get(CONF_DEVICE_MODEL, "Heating Actuator"),
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            devices_to_add.append(instance)
        else:
            LOGGER.warning(f"Unsupported WHO value '{who}' for switch configuration: {device_id}")

    if devices_to_add:
        async_add_entities(devices_to_add)
        LOGGER.info(f"Added {len(devices_to_add)} MyHome switch entities.")
    else:
        LOGGER.info("No MyHome switch entities to add.")


async def async_unload_entry(hass, config_entry):
    # La logica di unload esistente sembra agire a livello di piattaforma e chiavi,
    # quindi potrebbe non necessitare modifiche immediate per il nuovo tipo,
    # ma assicurati che sia robusta se la configurazione cambia dinamicamente.
    if PLATFORM not in hass.data[DOMAIN].get(config_entry.data[CONF_MAC], {}).get(CONF_PLATFORMS, {}):
        return True

    # Questo è un unload semplificato. Una gestione completa potrebbe essere più complessa.
    # Ad esempio, se le entità sono tracciate, dovrebbero essere rimosse esplicitamente.
    # Per ora, si assume che la rimozione dei dati dalla config porti HA a rimuovere le entità.
    
    # Rimuovi la configurazione per la piattaforma SWITCH
    hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS].pop(PLATFORM, None)
    LOGGER.info(f"MyHome switch platform unloaded for gateway {config_entry.data[CONF_MAC]}.")
    return True


class MyHOMESwitch(MyHOMEEntity, SwitchEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str,
        where: str,
        interface: str,
        device_class: str,
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name, # Questo è il nome 'principale' del dispositivo MyHome
            platform=PLATFORM,
            device_id=device_id, # Usato per object_id in HA
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        # Il nome visualizzato dall'entità in HA
        self._attr_name = entity_name if entity_name else name

        self._interface = interface
        # _full_where è specifico per WHO=1 che potrebbe usare l'interfaccia
        self._full_where = f"{self._where}#4#{self._interface}" if self._interface is not None else self._where
        
        # Questi attributi extra potrebbero non essere rilevanti per tutti i tipi di WHERE
        try:
            if who == "1" and not where.startswith("#") and not where == "0" and len(where) % 2 == 0 and where.isalnum(): # Tipico PointToPoint A/PL
                 self._attr_extra_state_attributes = {
                    "A": where[: len(where) // 2],
                    "PL": where[len(where) // 2 :],
                }
                 if self._interface is not None:
                    self._attr_extra_state_attributes["Int"] = self._interface
            else: # Per Generale, Gruppo o altri formati
                self._attr_extra_state_attributes = {}

        except TypeError: # In caso where sia None o non stringa
             self._attr_extra_state_attributes = {}


        self._attr_device_class = SwitchDeviceClass.OUTLET if device_class and device_class.lower() == "outlet" else SwitchDeviceClass.SWITCH

        self._on_icon = icon_on
        self._off_icon = icon

        if self._off_icon is not None:
            self._attr_icon = self._off_icon
        else: # Default icon se non specificato
            self._attr_icon = "mdi:toggle-switch-off-outline"


        self._attr_is_on = None
        LOGGER.debug(f"Initialized MyHOMESwitch (WHO=1): {self.name} ({self.unique_id})")


    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._attr_is_on

    async def async_update(self):
        """Update the entity."""
        LOGGER.debug(f"Requesting update for MyHOMESwitch {self._full_where} ({self.name})")
        await self._gateway_handler.send_status_request(OWNLightingCommand.status(self._full_where))

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device on."""
        LOGGER.info(f"Turning ON MyHOMESwitch {self._full_where} ({self.name})")
        await self._gateway_handler.send(OWNLightingCommand.switch_on(self._full_where))
        # Optimistic update
        # self._attr_is_on = True
        # self._update_icon()
        # self.async_write_ha_state()


    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device off."""
        LOGGER.info(f"Turning OFF MyHOMESwitch {self._full_where} ({self.name})")
        await self._gateway_handler.send(OWNLightingCommand.switch_off(self._full_where))
        # Optimistic update
        # self._attr_is_on = False
        # self._update_icon()
        # self.async_write_ha_state()

    def _update_icon(self):
        if self._off_icon is not None and self._on_icon is not None:
            self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        elif self._attr_is_on:
            self._attr_icon = "mdi:toggle-switch-variant"
        else:
            self._attr_icon = "mdi:toggle-switch-off-outline"


    def handle_event(self, message: OWNLightingEvent):
        """Handle an event message."""
        # Assumiamo che MyHOMEEntity filtri gli eventi per unique_id
        
        log_prefix = "Switch" # Default
        if self._attr_device_class == SwitchDeviceClass.OUTLET:
            log_prefix = "Outlet"
        
        LOGGER.info(
            "%s %s: Received lighting event: %s. New state: %s",
            self._gateway_handler.log_id, # Assumendo che log_id sia nel gateway_handler
            self.name,
            message.human_readable_log.replace("Light", log_prefix),
            "ON" if message.is_on else "OFF"
        )
        
        new_state = message.is_on
        if self._attr_is_on != new_state:
            self._attr_is_on = new_state
            self._update_icon()
            self.async_schedule_update_ha_state()

# Nuova classe per il Termoarredo (WHO=4, Dimensione 20)
class MyHomeActuatorSwitch(MyHOMEEntity, SwitchEntity):
    """Representation of a MyHome Heating Actuator (WHO=4, DIM=20) as a Switch."""

    def __init__(
        self,
        hass,
        name: str,           # Nome principale dalla config YAML per il dispositivo MyHome
        entity_name: str,    # Nome specifico per l'entità HA se diverso
        icon: str,           # Icona spento
        icon_on: str,        # Icona acceso
        device_id: str,      # Usato per l'object_id di HA
        who: str,
        where: str,          # Formato atteso: ZN, es. "91"
        device_class: str,   # "switch" o "outlet"
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name, # Nome del dispositivo MyHome
            platform=PLATFORM, # Dominio SWITCH
            device_id=device_id, # Usato per object_id
            who=who,
            where=where, # Qui WHERE è ZN
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )
        # Nome dell'entità in Home Assistant
        self._attr_name = entity_name if entity_name else name
        
        # Non c'è _full_where con interfaccia per questo tipo
        # self._full_where = where # Usiamo direttamente self._where ereditato
        self._full_where = f"{self._where}#1" 
        self._attr_device_class = SwitchDeviceClass.OUTLET if device_class and device_class.lower() == "outlet" else SwitchDeviceClass.SWITCH
        
        self._on_icon = icon_on
        self._off_icon = icon

        if self._off_icon is not None:
            self._attr_icon = self._off_icon
        else: # Icona di default per termoarredo/switch generico
            self._attr_icon = "mdi:radiator-disabled" if self._attr_device_class == SwitchDeviceClass.SWITCH else "mdi:power-plug-off"


        self._attr_is_on = None # Stato iniziale
        LOGGER.debug(f"Initialized MyHomeActuatorSwitch (WHO=4): {self.name} ({self.unique_id})")

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the actuator on."""
        LOGGER.info(f"Turning ON Actuator (Termoarredo) {self._where} for {self.name}")
        await self._gateway_handler.send(
            OWNHeatingCommand.set_actuator_on(self._where) # self._where è Z#N
        )
        # Optimistic update
        # self._attr_is_on = True
        # self._update_icon()
        # self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the actuator off."""
        LOGGER.info(f"Turning OFF Actuator (Termoarredo) {self._where} for {self.name}")
        await self._gateway_handler.send(
            OWNHeatingCommand.set_actuator_off(self._where) # self._where è Z#N
        )
        # Optimistic update
        # self._attr_is_on = False
        # self._update_icon()
        # self.async_write_ha_state()
        
    def _update_icon(self):
        if self._off_icon is not None and self._on_icon is not None:
            self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon
        elif self._attr_is_on:
            # Icona di default per termoarredo acceso
            self._attr_icon = "mdi:radiator" if self._attr_device_class == SwitchDeviceClass.SWITCH else "mdi:power-plug"
        else:
            # Icona di default per termoarredo spento
            self._attr_icon = "mdi:radiator-disabled" if self._attr_device_class == SwitchDeviceClass.SWITCH else "mdi:power-plug-off"


    async def async_update(self) -> None:
        """Request state update for the actuator."""
        LOGGER.debug(f"Requesting update for Actuator (Termoarredo) {self._where} ({self.name})")
        await self._gateway_handler.send_status_request( 
            OWNHeatingCommand.get_actuator_status(self._where) # self._where è Z#N
        )

    def handle_event(self, message: OWNHeatingEvent) -> None:
        """Handle an event message from the gateway for WHO=4."""
        LOGGER.info(
        f"{self.name} (Termoarredo) received event: WHO={message.who}, WHERE={message.where}, "
        f"DIM={message.dimension}, VALUE={message._dimension_value}, RAW={message._raw}"
    )
        # La classe base MyHOMEEntity dovrebbe aver già filtrato per unique_id (who-where)
        
        # Verifica che sia un evento di stato per un attuatore (Dimensione 20)
        if message.dimension == 20: 
            # message.is_active() da OWNHeatingEvent per dim=20:
            # True se dimension_value[0] è "1" (ON)
            # False se dimension_value[0] è "0" (OFF)
            new_state = message.is_active()
            
            LOGGER.info(
                "%s %s (Termoarredo): Received actuator status event. Raw value: '%s', Parsed state: %s",
                self._gateway_handler.log_id, # Assumendo log_id nel gateway_handler
                self.name,
                message._dimension_value[0], # Valore grezzo (stringa "0" o "1")
                "ON" if new_state else "OFF"
            )

            if self._attr_is_on != new_state:
                self._attr_is_on = new_state
                self._update_icon()
                self.async_schedule_update_ha_state()
        # else:
            # LOGGER.debug(f"{self.name} (Termoarredo) received unhandled WHO=4 event: DIM={message.dimension}")