"""Support for MyHome switches (light modules used for controlled outlets, relays AND thermo actuators)."""
from homeassistant.components.switch import (
    DOMAIN as PLATFORM,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
    CONF_ENTITIES, # Aggiunto se mancante dalle tue costanti
)

from OWNd.message import (
    OWNLightingEvent,
    OWNLightingCommand,
    OWNHeatingEvent,       # <-- NUOVA IMPORTAZIONE
    OWNHeatingCommand,     # <-- NUOVA IMPORTAZIONE
)

from .const import (
    CONF_PLATFORMS,
    CONF_ENTITY,
    CONF_ENTITY_NAME,
    CONF_ICON,
    CONF_ICON_ON,
    CONF_WHO,
    CONF_WHERE,
    CONF_BUS_INTERFACE, # Assicurati sia definito
    CONF_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_CLASS, # Assicurati sia definito
    DOMAIN,
    LOGGER,
)
from .myhome_device import MyHOMEEntity
from .gateway import MyHOMEGatewayHandler


async def async_setup_entry(hass, config_entry, async_add_entities):
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    _switches = []
    _configured_switches = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]

    for _switch_id in _configured_switches.keys(): # Rinominato _switch a _switch_id
        config_data = _configured_switches[_switch_id]
        who = config_data[CONF_WHO]

        if who == "1": # Logica esistente per interruttori basati su luci (WHO=1)
            entity = MyHOMESwitch(
                hass=hass,
                device_id=_switch_id,
                who=config_data[CONF_WHO],
                where=config_data[CONF_WHERE],
                icon=config_data.get(CONF_ICON), # Usare .get() per opzionali
                icon_on=config_data.get(CONF_ICON_ON), # Usare .get() per opzionali
                interface=config_data.get(CONF_BUS_INTERFACE), # Usare .get() per opzionali
                name=config_data[CONF_NAME],
                entity_name=config_data[CONF_ENTITY_NAME],
                device_class=config_data.get(CONF_DEVICE_CLASS, "switch"), # Default a switch
                manufacturer=config_data[CONF_MANUFACTURER],
                model=config_data[CONF_DEVICE_MODEL],
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            _switches.append(entity)
        elif who == "4": # NUOVA LOGICA per attuatori Termo (WHO=4) come scaldasalviette
            # Per gli attuatori termo, CONF_WHERE dovrebbe essere Z#N
            # CONF_DEVICE_CLASS potrebbe essere "switch" o un nuovo tipo se vuoi distinguerlo
            entity = MyHOMEThermoActuatorSwitch( # Nuova classe
                hass=hass,
                device_id=_switch_id,
                who=config_data[CONF_WHO], # Sarà "4"
                where=config_data[CONF_WHERE], # Deve essere "Z#N"
                name=config_data[CONF_NAME],
                entity_name=config_data[CONF_ENTITY_NAME],
                # device_class non è usato direttamente da SwitchEntity come per BinarySensor,
                # ma potremmo usarlo per logica interna o attributi se necessario.
                # SwitchDeviceClass.SWITCH è implicito se non si specifica outlet.
                manufacturer=config_data[CONF_MANUFACTURER],
                model=config_data.get(CONF_DEVICE_MODEL, "Thermo Actuator Switch"), # Modello di default
                gateway=hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_ENTITY],
            )
            _switches.append(entity)


    async_add_entities(_switches)


async def async_unload_entry(hass, config_entry): # Funzione di unload esistente
    if PLATFORM not in hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS]:
        return True

    # Non è necessario iterare e cancellare uno per uno qui se la piattaforma
    # viene rimossa completamente. La struttura dati verrà eliminata da HA.
    # Tuttavia, se si vuole essere precisi per la cancellazione di singole entità:
    # _configured_switches = hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM]
    # for _switch_id in list(_configured_switches.keys()): # list() per evitare errori di dimensione durante iterazione
    #     del hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS][PLATFORM][_switch_id]
    # Se si rimuove l'intera piattaforma per la entry:
    hass.data[DOMAIN][config_entry.data[CONF_MAC]][CONF_PLATFORMS].pop(PLATFORM, None)
    return True


class MyHOMESwitch(MyHOMEEntity, SwitchEntity): # Classe esistente
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        icon: str,
        icon_on: str,
        device_id: str,
        who: str, # Sarà "1"
        where: str,
        interface: str,
        device_class: str, # "outlet" o "switch"
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name,
            platform=PLATFORM,
            device_id=device_id,
            who=who,
            where=where,
            manufacturer=manufacturer,
            model=model,
            gateway=gateway,
        )

        self._attr_name = entity_name if entity_name else name # Nome entità più specifico

        self._interface = interface
        # _full_where è specifico per comandi luci con interfaccia bus,
        # non necessario per attuatori termo WHO=4 che usano Z#N direttamente.
        self._full_where = f"{self._where}#4#{self._interface}" if self._interface is not None else self._where

        self._attr_extra_state_attributes = {
            "openwebnet_who": self._who,
            "openwebnet_where": self._where, # Where originale senza interfaccia
        }
        if self._interface is not None: #
            self._attr_extra_state_attributes["bus_interface"] = self._interface #

        if device_class and device_class.lower() == "outlet":
            self._attr_device_class = SwitchDeviceClass.OUTLET
        else:
            self._attr_device_class = SwitchDeviceClass.SWITCH

        self._on_icon = icon_on
        self._off_icon = icon

        if self._off_icon is not None:
            self._attr_icon = self._off_icon

        self._attr_is_on = None # Stato iniziale

    async def async_update(self):
        """Update the entity."""
        # Per WHO=1 (luci/attuatori), usa OWNLightingCommand
        await self._gateway_handler.send_status_request(OWNLightingCommand.status(self._full_where))

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device on."""
        await self._gateway_handler.send(OWNLightingCommand.switch_on(self._full_where))

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the device off."""
        await self._gateway_handler.send(OWNLightingCommand.switch_off(self._full_where))

    def handle_event(self, message: OWNLightingEvent): # Gestisce eventi WHO=1
        """Handle an event message."""
        # Assicurati che l'evento sia per questa entità
        if message.unique_id != self.unique_id: # Confronto ID univoco
             return

        log_message_prefix = ""
        if self._attr_device_class == SwitchDeviceClass.SWITCH:
            log_message_prefix = "Switch"
        elif self._attr_device_class == SwitchDeviceClass.OUTLET:
            log_message_prefix = "Outlet"
        
        LOGGER.info(
            "%s %s: %s",
            self._gateway_handler.log_id,
            log_message_prefix,
            message.human_readable_log.replace("Light", log_message_prefix if log_message_prefix else "Device"),
        )
        self._attr_is_on = message.is_on #
        if self._off_icon is not None and self._on_icon is not None: #
            self._attr_icon = self._on_icon if self._attr_is_on else self._off_icon #
        self.async_schedule_update_ha_state()


# NUOVA CLASSE PER LO SCALDASALVIETTE/ATUATTORE TERMO COME SWITCH
class MyHOMEThermoActuatorSwitch(MyHOMEEntity, SwitchEntity):
    def __init__(
        self,
        hass,
        name: str,
        entity_name: str,
        device_id: str,
        who: str, # Sarà "4"
        where: str, # Sarà "Z#N"
        manufacturer: str,
        model: str,
        gateway: MyHOMEGatewayHandler,
    ):
        super().__init__(
            hass=hass,
            name=name, # Nome del dispositivo MyHOME generico
            platform=PLATFORM, #
            device_id=device_id, # ID univoco dell'entità HA
            who=who, #
            where=where, # L'indirizzo Z#N dell'attuatore
            manufacturer=manufacturer, #
            model=model, #
            gateway=gateway, #
        )

        self._attr_name = entity_name if entity_name else f"Thermo Actuator {self._where}" # Nome entità HA
        self._attr_device_class = SwitchDeviceClass.SWITCH # È un interruttore generico
        
        # unique_id è già impostato in MyHOMEEntity come f"{gateway.mac}-{self._device_id}"
        # o f"{gateway.mac}-{self._who}-{self._where}" a seconda di MyHOMEEntity
        # Assicuriamoci che sia coerente con come vengono matchati gli eventi
        # self._attr_unique_id = f"{gateway.mac}-{self._who}-{self._where}" # Sovrascrivi se necessario per coerenza con l'evento
        
        self._attr_extra_state_attributes = {
            "openwebnet_who": self._who,
            "openwebnet_where": self._where,
        }
        self._attr_is_on = None # Stato iniziale

    async def async_update(self):
        """Update the entity by requesting actuator status."""
        # Usa OWNHeatingCommand per richiedere lo stato dell'attuatore (Dimensione 20)
        # Assicurati che OWNHeatingCommand.request_actuator_status(self._where) sia implementato
        # e che self._where (Z#N) sia l'indirizzo corretto.
        if hasattr(OWNHeatingCommand, "request_actuator_status"):
            await self._gateway_handler.send_status_request(
                OWNHeatingCommand.request_actuator_status(self._where)
            )
        else:
            LOGGER.warning(f"OWNHeatingCommand.request_actuator_status method not found for {self.name}")

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the thermo actuator on."""
        # Usa OWNHeatingCommand per accendere l'attuatore (Dimensione 20, valore 1)
        if hasattr(OWNHeatingCommand, "set_actuator_on"):
            await self._gateway_handler.send(
                OWNHeatingCommand.set_actuator_on(self._where)
            )
            self._attr_is_on = True # Assumi successo per risposta UI più rapida
            self.async_schedule_update_ha_state() #
        else:
            LOGGER.warning(f"OWNHeatingCommand.set_actuator_on method not found for {self.name}")


    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn the thermo actuator off."""
        # Usa OWNHeatingCommand per spegnere l'attuatore (Dimensione 20, valore 0)
        if hasattr(OWNHeatingCommand, "set_actuator_off"):
            await self._gateway_handler.send(
                OWNHeatingCommand.set_actuator_off(self._where)
            )
            self._attr_is_on = False # Assumi successo
            self.async_schedule_update_ha_state() #
        else:
            LOGGER.warning(f"OWNHeatingCommand.set_actuator_off method not found for {self.name}")


    def handle_event(self, message: OWNHeatingEvent): # Gestisce eventi WHO=4
        """Handle an event message for WHO=4, Dimension 20 (actuator status)."""
        # Verifica che l'evento sia per questo specifico attuatore
        # Il unique_id dell'evento dovrebbe essere "4-Z#N"
        # Il unique_id di questa entità (da MyHOMEEntity) è f"{self._who}-{self._where}" -> "4-Z#N"
        if not (message.who == 4 and message.dimension == 20 and message.unique_id == self.unique_id):
            return

        LOGGER.info(
            "%s Thermo Actuator Switch (%s): %s",
            self._gateway_handler.log_id,
            self._where,
            message.human_readable_log,
        )
        
        try:
            actuator_state_value = int(message._dimension_value[0])
            if actuator_state_value == 1: # Attuatore ON
                self._attr_is_on = True
            elif actuator_state_value == 0: # Attuatore OFF
                self._attr_is_on = False
            else:
                # Altri stati (2-9 per ventole, ecc.) non cambiano lo stato ON/OFF di un semplice switch
                LOGGER.debug(f"Thermo Actuator Switch {self._where} received unhandled state value {actuator_state_value} for ON/OFF state.")
                return # Non aggiornare lo stato se non è 0 o 1 per un interruttore semplice
            
            self.async_schedule_update_ha_state()

        except (ValueError, IndexError) as e:
            LOGGER.error(f"Error processing thermo actuator event for {self._where}: {e} - Data: {message._raw}")