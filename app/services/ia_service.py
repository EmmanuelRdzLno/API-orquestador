import os
import json, re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def preguntar_a_openai(messages, max_tokens, temperature):
    """Consulta genérica a OpenAI con historial de mensajes"""
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        system_prompt = {
            "role": "system",
            "content": (
                f"Eres un asistente de WhatsApp que puede orquestar múltiples servicios:\n"
                f"- FACTURACIÓN (consultar_facturas, descargar_documento, crear_factura)\n"
                f"- WHATSAPP (responder al usuario de forma humanizada)\n"
                f"La fecha actual es {fecha_actual}.\n"
                "Siempre analiza el historial y los roles (assistant, user, etc) para enteder el contexto y decide el siguiente paso a ejecutar.\n"
                "Responde siempre breve y precisa.\n"
                "Si el siguiente paso es WHATSAPP, significa que ya tienes toda la información y puedes redactar la respuesta final."
            )
        }
        all_messages = [system_prompt] + messages
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=all_messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error en OpenAI: {e}")
        return None

async def clasificar_siguiente_paso(historial):
    """
    Dado el historial completo (usuario + resultados de funciones),
    indica el siguiente servicio y función a ejecutar.
    Formato esperado:
    {
      "servicio": "FACTURACION" | "WHATSAPP",
      "funcion": "consultar_facturas" | "descargar_documento" | "crear_factura" | "respuesta_final",
      "params": { ... }
    }
    """
    prompt = """
    Analiza el historial del asistente y determina el siguiente paso.
    Servicios posibles:
    - FACTURACION:
        consultar_facturas: Obtienes un JSON con los datos de factura/s
        descargar_documento: Obtienes el tipo de archivo (pdf o xml) con el id de la factura
        crear_factura: Funcion para emitir una factura. IMPORTANTE! solicita toda la informacion al cliente: 1. Partidas de lo que se va a facturar, 2. Datos fiscales del receptor (considera las obligaciones fiscales del receptor para emitir correctamente la factura, impuestos a doc a sus obligaciones), 3. Tipo de factura, 4. Forma de pago, etc. 
    - WHATSAPP:
        respuesta_final: Funcion para mandar mensaje al usuario.

    Devuelve SOLO un JSON con:
    {
      "servicio": "...",
      "funcion": "..."
    }
    """
    messages = historial + [{"role": "user", "content": prompt}]
    max_tokens=50
    temperature=0.1
    respuesta = await preguntar_a_openai(messages, max_tokens, temperature)

    # Buscar cualquier objeto JSON en la respuesta
    match = re.search(r'(\{[\s\S]*\})', respuesta)
    if match:
        bloque = match.group(1)
        try:
            siguiente = json.loads(bloque)
            if not siguiente:
                return None
            servicio = (siguiente.get("servicio") or "").upper()
            funcion = siguiente.get("funcion", "")

            if servicio == "FACTURACION" or servicio == "FACTURACIÓN":
                if funcion == "consultar_facturas":
                    """
                    Cargar prompt de consultar facturas con datos especificos para que openai tenga mas claridad sobre la accion a ejecutar
                    """
                    prompt = """
                    Ejecuta la funcion con los paremtros necesarios para cumplir con este paso solicitado de acuerdo al historial del asistente.
                    Servicio que requieres:
                    - FACTURACION:
                        consultar_facturas(params): Obtienes un JSON con los datos de factura/s, puedes filtrar con 1 o varios parámetros
                            parametros:
                                type: issued/recived/payroll
                                folioStart: inicio de folios
                                folioEnd: final de folios
                                rfc: rfc del receptor de la factura a consultar
                                dateStart: fecha de inicio de la factura
                                dateEnd: fecha final de la factura
                                status: all/active/canceled/pending estado de la factura del CFDI

                    Devuelve SOLO un JSON con:
                    {
                    "servicio": "FACTURACION",
                    "funcion": "consultar_facturas"
                    "params": { ... }
                    }
                    """
                    max_tokens = 150
                    temperature = 0.1
                if funcion == "descargar_documento":
                    """
                    Cargar prompt de descargar facturas con datos especificos para que openai tenga mas claridad sobre la accion a ejecutar
                    """
                    prompt = """
                    Ejecuta la funcion con los paremtros necesarios para cumplir con este paso solicitado de acuerdo al historial del asistente.
                    Servicio que requieres:
                    - FACTURACION:
                        descargar_documento(params): Obtienes el tipo de archivo (pdf o xml) con el id de la factura, todos los parametros son obligatorios
                            parametros:
                                id: id de la factura
                                format: pdf/xml tipo de formato
                                type: issued/recived/payroll

                    Devuelve SOLO un JSON con:
                    {
                    "servicio": "FACTURACION",
                    "funcion": "descargar_documento"
                    "params": { ... }
                    }
                    """
                    max_tokens = 100
                    temperature = 0.1
                if funcion == "crear_factura":
                    """
                    Cargar prompt de crear factura con datos especificos para que openai tenga mas claridad sobre la accion a ejecutar
                    """
                    prompt = """
                    Ejecuta la funcion con los paremtros necesarios para cumplir con este paso solicitado de acuerdo al historial del asistente.
                    Servicio que requieres:
                    - FACTURACION:
                        crear_factura(params): Funcion para generar factura, IMPORTANTE: siempre los parametros obligatorios son los relacionados con el tipo de factura, los de Items, los de Taxes y los de Receiver. Considera los datos del emisor: RFC=ROLE930613SC5, RAZÓN SOCIAL= EMMANUEL DE JESUS RODRIGUEZ LUEVANO, CODIGO POSTAL=20160, REGIMEN FISCAL=RESICO.
                            ejemplo de parametros:
                                {
                                    "NameId": 1,
                                    "Date": "sample string 1",
                                    "Serie": "sample string 2",
                                    "PaymentAccountNumber": "sample string 3",
                                    "CurrencyExchangeRate": 1.0,
                                    "Currency": "sample string 4",
                                    "Confirmation": "sample string 5",
                                    "ExpeditionPlace": "sample string 6",
                                    "Exportation": "sample string 7",
                                    "PaymentConditions": "sample string 8",
                                    "Relations": {
                                        "Type": "sample string 1",
                                        "Cfdis": [
                                        {
                                            "Uuid": "sample string 1"
                                        },
                                        {
                                            "Uuid": "sample string 1"
                                        }
                                        ]
                                    },
                                    "GlobalInformation": {
                                        "Periodicity": "sample string 1",
                                        "Months": "sample string 2",
                                        "Year": 3
                                    },
                                    "IsInvoice": true,
                                    "IdCfdi": "sample string 9",
                                    "Folio": "sample string 10",
                                    "CfdiType": "sample string 11",
                                    "PaymentForm": "sample string 12",
                                    "PaymentMethod": "sample string 13",
                                    "Receiver": {
                                        "Id": "sample string 1",
                                        "Rfc": "sample string 2",
                                        "Name": "sample string 3",
                                        "CfdiUse": "sample string 4",
                                        "FiscalRegime": "sample string 5",
                                        "TaxZipCode": "sample string 6",
                                        "TaxResidence": "sample string 7",
                                        "TaxRegistrationNumber": "sample string 8",
                                        "Address": {
                                        "Street": "sample string 1",
                                        "ExteriorNumber": "sample string 2",
                                        "InteriorNumber": "sample string 3",
                                        "Neighborhood": "sample string 4",
                                        "ZipCode": "sample string 5",
                                        "Locality": "sample string 6",
                                        "Municipality": "sample string 7",
                                        "State": "sample string 8",
                                        "Country": "sample string 9",
                                        "Id": "sample string 10"
                                        }
                                    },
                                    "Items": [
                                        {
                                        "IdProduct": "sample string 1",
                                        "ProductCode": "sample string 2",
                                        "IdentificationNumber": "sample string 3",
                                        "SKU": "sample string 4",
                                        "Description": "sample string 5",
                                        "Unit": "sample string 6",
                                        "UnitCode": "sample string 7",
                                        "UnitPrice": 8.0,
                                        "Quantity": 9.0,
                                        "Subtotal": 10.0,
                                        "Discount": 1.0,
                                        "TaxObject": "sample string 11",
                                        "Taxes": [
                                            {
                                            "Total": 1.0,
                                            "Name": "sample string 2",
                                            "Base": 3.0,
                                            "Rate": 4.0,
                                            "IsRetention": true,
                                            "IsQuota": true,
                                            "TaxObject": "sample string 6"
                                            },
                                            {
                                            "Total": 1.0,
                                            "Name": "sample string 2",
                                            "Base": 3.0,
                                            "Rate": 4.0,
                                            "IsRetention": true,
                                            "IsQuota": true,
                                            "TaxObject": "sample string 6"
                                            }
                                        ],
                                        "ThirdPartyAccount": {
                                            "Rfc": "sample string 1",
                                            "Name": "sample string 2",
                                            "FiscalRegime": "sample string 3",
                                            "TaxZipCode": "sample string 4"
                                        },
                                        "PropertyTaxIDNumber": [
                                            "sample string 1",
                                            "sample string 2"
                                        ],
                                        "NumerosPedimento": [
                                            "sample string 1",
                                            "sample string 2"
                                        ],
                                        "Parts": [
                                            {
                                            "Quantity": 1.0,
                                            "UnitCode": "sample string 2",
                                            "ProductCode": "sample string 3",
                                            "IdentificationNumber": "sample string 4",
                                            "Description": "sample string 5",
                                            "UnitPrice": 1.0,
                                            "Amount": 1.0,
                                            "CustomsInformation": [
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                },
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                }
                                            ]
                                            },
                                            {
                                            "Quantity": 1.0,
                                            "UnitCode": "sample string 2",
                                            "ProductCode": "sample string 3",
                                            "IdentificationNumber": "sample string 4",
                                            "Description": "sample string 5",
                                            "UnitPrice": 1.0,
                                            "Amount": 1.0,
                                            "CustomsInformation": [
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                },
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                }
                                            ]
                                            }
                                        ],
                                        "Total": 12.0,
                                        "Complement": {
                                            "EducationalInstitution": {
                                            "StudentsName": "sample string 1",
                                            "Curp": "sample string 2",
                                            "EducationLevel": "sample string 3",
                                            "AutRvoe": "sample string 4",
                                            "PaymentRfc": "sample string 5"
                                            },
                                            "ThirdPartyAccount": {
                                            "Rfc": "sample string 1",
                                            "Name": "sample string 2",
                                            "FiscalRegime": "sample string 3",
                                            "TaxZipCode": "sample string 4",
                                            "ThirdTaxInformation": {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Locality": "sample string 5",
                                                "Reference": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "PostalCode": "sample string 10",
                                                "ZipCode": "sample string 11"
                                            },
                                            "CustomsInformation": {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                            },
                                            "Parts": [
                                                {
                                                "Quantity": 1.0,
                                                "Unit": "sample string 2",
                                                "IdentificationNumber": "sample string 3",
                                                "Description": "sample string 4",
                                                "UnitPrce": 1.0,
                                                "Amount": 1.0,
                                                "CustomsInformation": [
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    },
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    }
                                                ]
                                                },
                                                {
                                                "Quantity": 1.0,
                                                "Unit": "sample string 2",
                                                "IdentificationNumber": "sample string 3",
                                                "Description": "sample string 4",
                                                "UnitPrce": 1.0,
                                                "Amount": 1.0,
                                                "CustomsInformation": [
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    },
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    }
                                                ]
                                                }
                                            ],
                                            "PropertyTaxNumber": "sample string 5",
                                            "Taxes": [
                                                {
                                                "Name": "sample string 1",
                                                "Rate": 1.0,
                                                "Amount": 2.0
                                                },
                                                {
                                                "Name": "sample string 1",
                                                "Rate": 1.0,
                                                "Amount": 2.0
                                                }
                                            ]
                                            }
                                        }
                                        },
                                        {
                                        "IdProduct": "sample string 1",
                                        "ProductCode": "sample string 2",
                                        "IdentificationNumber": "sample string 3",
                                        "SKU": "sample string 4",
                                        "Description": "sample string 5",
                                        "Unit": "sample string 6",
                                        "UnitCode": "sample string 7",
                                        "UnitPrice": 8.0,
                                        "Quantity": 9.0,
                                        "Subtotal": 10.0,
                                        "Discount": 1.0,
                                        "TaxObject": "sample string 11",
                                        "Taxes": [
                                            {
                                            "Total": 1.0,
                                            "Name": "sample string 2",
                                            "Base": 3.0,
                                            "Rate": 4.0,
                                            "IsRetention": true,
                                            "IsQuota": true,
                                            "TaxObject": "sample string 6"
                                            },
                                            {
                                            "Total": 1.0,
                                            "Name": "sample string 2",
                                            "Base": 3.0,
                                            "Rate": 4.0,
                                            "IsRetention": true,
                                            "IsQuota": true,
                                            "TaxObject": "sample string 6"
                                            }
                                        ],
                                        "ThirdPartyAccount": {
                                            "Rfc": "sample string 1",
                                            "Name": "sample string 2",
                                            "FiscalRegime": "sample string 3",
                                            "TaxZipCode": "sample string 4"
                                        },
                                        "PropertyTaxIDNumber": [
                                            "sample string 1",
                                            "sample string 2"
                                        ],
                                        "NumerosPedimento": [
                                            "sample string 1",
                                            "sample string 2"
                                        ],
                                        "Parts": [
                                            {
                                            "Quantity": 1.0,
                                            "UnitCode": "sample string 2",
                                            "ProductCode": "sample string 3",
                                            "IdentificationNumber": "sample string 4",
                                            "Description": "sample string 5",
                                            "UnitPrice": 1.0,
                                            "Amount": 1.0,
                                            "CustomsInformation": [
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                },
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                }
                                            ]
                                            },
                                            {
                                            "Quantity": 1.0,
                                            "UnitCode": "sample string 2",
                                            "ProductCode": "sample string 3",
                                            "IdentificationNumber": "sample string 4",
                                            "Description": "sample string 5",
                                            "UnitPrice": 1.0,
                                            "Amount": 1.0,
                                            "CustomsInformation": [
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                },
                                                {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                                }
                                            ]
                                            }
                                        ],
                                        "Total": 12.0,
                                        "Complement": {
                                            "EducationalInstitution": {
                                            "StudentsName": "sample string 1",
                                            "Curp": "sample string 2",
                                            "EducationLevel": "sample string 3",
                                            "AutRvoe": "sample string 4",
                                            "PaymentRfc": "sample string 5"
                                            },
                                            "ThirdPartyAccount": {
                                            "Rfc": "sample string 1",
                                            "Name": "sample string 2",
                                            "FiscalRegime": "sample string 3",
                                            "TaxZipCode": "sample string 4",
                                            "ThirdTaxInformation": {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Locality": "sample string 5",
                                                "Reference": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "PostalCode": "sample string 10",
                                                "ZipCode": "sample string 11"
                                            },
                                            "CustomsInformation": {
                                                "Number": "sample string 1",
                                                "Date": "sample string 2",
                                                "Customs": "sample string 3"
                                            },
                                            "Parts": [
                                                {
                                                "Quantity": 1.0,
                                                "Unit": "sample string 2",
                                                "IdentificationNumber": "sample string 3",
                                                "Description": "sample string 4",
                                                "UnitPrce": 1.0,
                                                "Amount": 1.0,
                                                "CustomsInformation": [
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    },
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    }
                                                ]
                                                },
                                                {
                                                "Quantity": 1.0,
                                                "Unit": "sample string 2",
                                                "IdentificationNumber": "sample string 3",
                                                "Description": "sample string 4",
                                                "UnitPrce": 1.0,
                                                "Amount": 1.0,
                                                "CustomsInformation": [
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    },
                                                    {
                                                    "Number": "sample string 1",
                                                    "Date": "sample string 2",
                                                    "Customs": "sample string 3"
                                                    }
                                                ]
                                                }
                                            ],
                                            "PropertyTaxNumber": "sample string 5",
                                            "Taxes": [
                                                {
                                                "Name": "sample string 1",
                                                "Rate": 1.0,
                                                "Amount": 2.0
                                                },
                                                {
                                                "Name": "sample string 1",
                                                "Rate": 1.0,
                                                "Amount": 2.0
                                                }
                                            ]
                                            }
                                        }
                                        }
                                    ],
                                    "Complemento": {
                                        "NotariosPublicos": {
                                        "DescInmuebles": [
                                            {
                                            "TipoInmueble": "sample string 1",
                                            "Calle": "sample string 2",
                                            "NoExterior": "sample string 3",
                                            "NoInterior": "sample string 4",
                                            "Colonia": "sample string 5",
                                            "Localidad": "sample string 6",
                                            "Referencia": "sample string 7",
                                            "Municipio": "sample string 8",
                                            "Estado": "sample string 9",
                                            "Pais": "sample string 10",
                                            "CodigoPostal": "sample string 11"
                                            },
                                            {
                                            "TipoInmueble": "sample string 1",
                                            "Calle": "sample string 2",
                                            "NoExterior": "sample string 3",
                                            "NoInterior": "sample string 4",
                                            "Colonia": "sample string 5",
                                            "Localidad": "sample string 6",
                                            "Referencia": "sample string 7",
                                            "Municipio": "sample string 8",
                                            "Estado": "sample string 9",
                                            "Pais": "sample string 10",
                                            "CodigoPostal": "sample string 11"
                                            }
                                        ],
                                        "DatosOperacion": {
                                            "NumInstrumentoNotarial": 1,
                                            "FechaInstNotarial": "sample string 2",
                                            "MontoOperacion": 3.0,
                                            "Subtotal": 4.0,
                                            "IVA": 5.0
                                        },
                                        "DatosNotario": {
                                            "CURP": "sample string 1",
                                            "NumNotaria": 2,
                                            "EntidadFederativa": "sample string 3",
                                            "Adscripcion": "sample string 4"
                                        },
                                        "DatosEnajenante": {
                                            "CoproSocConyugalE": "sample string 1",
                                            "DatosUnEnajenante": {
                                            "Nombre": "sample string 1",
                                            "ApellidoPaterno": "sample string 2",
                                            "ApellidoMaterno": "sample string 3",
                                            "RFC": "sample string 4",
                                            "CURP": "sample string 5"
                                            },
                                            "DatosEnajenanteCopSC": {
                                            "DatosEnajenanteCopSC": [
                                                {
                                                "Porcentaje": 1.0,
                                                "Nombre": "sample string 2",
                                                "ApellidoPaterno": "sample string 3",
                                                "ApellidoMaterno": "sample string 4",
                                                "RFC": "sample string 5",
                                                "CURP": "sample string 6"
                                                },
                                                {
                                                "Porcentaje": 1.0,
                                                "Nombre": "sample string 2",
                                                "ApellidoPaterno": "sample string 3",
                                                "ApellidoMaterno": "sample string 4",
                                                "RFC": "sample string 5",
                                                "CURP": "sample string 6"
                                                }
                                            ]
                                            }
                                        },
                                        "DatosAdquiriente": {
                                            "CoproSocConyugalE": "sample string 1",
                                            "DatosUnAdquiriente": {
                                            "Nombre": "sample string 1",
                                            "ApellidoPaterno": "sample string 2",
                                            "ApellidoMaterno": "sample string 3",
                                            "RFC": "sample string 4",
                                            "CURP": "sample string 5"
                                            },
                                            "DatosAdquirienteCopSC": {
                                            "DatosAdquirienteCopSC": [
                                                {
                                                "Porcentaje": 1.0,
                                                "Nombre": "sample string 2",
                                                "ApellidoPaterno": "sample string 3",
                                                "ApellidoMaterno": "sample string 4",
                                                "RFC": "sample string 5",
                                                "CURP": "sample string 6"
                                                },
                                                {
                                                "Porcentaje": 1.0,
                                                "Nombre": "sample string 2",
                                                "ApellidoPaterno": "sample string 3",
                                                "ApellidoMaterno": "sample string 4",
                                                "RFC": "sample string 5",
                                                "CURP": "sample string 6"
                                                }
                                            ]
                                            }
                                        }
                                        },
                                        "Ine": {},
                                        "Detallista": {},
                                        "Payments": [
                                        {
                                            "SignPayment": "sample string 1",
                                            "CertPayment": "sample string 2",
                                            "OriginalString": "sample string 3",
                                            "StringTypePayment": "sample string 4",
                                            "RelatedDocuments": [
                                            {
                                                "Uuid": "sample string 1",
                                                "Serie": "sample string 2",
                                                "Folio": "sample string 3",
                                                "Currency": "sample string 4",
                                                "EquivalenceDocRel": 1.0,
                                                "ExchangeRate": 1.0,
                                                "PartialityNumber": 1,
                                                "PreviousBalanceAmount": 1.0,
                                                "AmountPaid": 1.0,
                                                "TaxObject": "sample string 5",
                                                "Taxes": [
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                },
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                }
                                                ]
                                            },
                                            {
                                                "Uuid": "sample string 1",
                                                "Serie": "sample string 2",
                                                "Folio": "sample string 3",
                                                "Currency": "sample string 4",
                                                "EquivalenceDocRel": 1.0,
                                                "ExchangeRate": 1.0,
                                                "PartialityNumber": 1,
                                                "PreviousBalanceAmount": 1.0,
                                                "AmountPaid": 1.0,
                                                "TaxObject": "sample string 5",
                                                "Taxes": [
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                },
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                }
                                                ]
                                            }
                                            ],
                                            "Taxes": [
                                            {
                                                "Total": 1.0,
                                                "Name": "sample string 2",
                                                "Base": 3.0,
                                                "Rate": 4.0,
                                                "IsRetention": true,
                                                "IsQuota": true,
                                                "TaxObject": "sample string 6"
                                            },
                                            {
                                                "Total": 1.0,
                                                "Name": "sample string 2",
                                                "Base": 3.0,
                                                "Rate": 4.0,
                                                "IsRetention": true,
                                                "IsQuota": true,
                                                "TaxObject": "sample string 6"
                                            }
                                            ],
                                            "Date": "sample string 5",
                                            "PaymentForm": "sample string 6",
                                            "Currency": "sample string 7",
                                            "ExchangeRate": 1.0,
                                            "Amount": 8.0,
                                            "OperationNumber": "sample string 9",
                                            "RfcIssuerPayerAccount": "sample string 10",
                                            "ForeignAccountNamePayer": "sample string 11",
                                            "PayerAccount": "sample string 12",
                                            "RfcReceiverBeneficiaryAccount": "sample string 13",
                                            "BeneficiaryAccount": "sample string 14",
                                            "ExpectedPaid": 2.0
                                        },
                                        {
                                            "SignPayment": "sample string 1",
                                            "CertPayment": "sample string 2",
                                            "OriginalString": "sample string 3",
                                            "StringTypePayment": "sample string 4",
                                            "RelatedDocuments": [
                                            {
                                                "Uuid": "sample string 1",
                                                "Serie": "sample string 2",
                                                "Folio": "sample string 3",
                                                "Currency": "sample string 4",
                                                "EquivalenceDocRel": 1.0,
                                                "ExchangeRate": 1.0,
                                                "PartialityNumber": 1,
                                                "PreviousBalanceAmount": 1.0,
                                                "AmountPaid": 1.0,
                                                "TaxObject": "sample string 5",
                                                "Taxes": [
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                },
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                }
                                                ]
                                            },
                                            {
                                                "Uuid": "sample string 1",
                                                "Serie": "sample string 2",
                                                "Folio": "sample string 3",
                                                "Currency": "sample string 4",
                                                "EquivalenceDocRel": 1.0,
                                                "ExchangeRate": 1.0,
                                                "PartialityNumber": 1,
                                                "PreviousBalanceAmount": 1.0,
                                                "AmountPaid": 1.0,
                                                "TaxObject": "sample string 5",
                                                "Taxes": [
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                },
                                                {
                                                    "Name": "sample string 1",
                                                    "Total": 2.0,
                                                    "Base": 3.0,
                                                    "Rate": 4.0,
                                                    "IsRetention": true,
                                                    "IsQuota": true,
                                                    "TaxObject": "sample string 6"
                                                }
                                                ]
                                            }
                                            ],
                                            "Taxes": [
                                            {
                                                "Total": 1.0,
                                                "Name": "sample string 2",
                                                "Base": 3.0,
                                                "Rate": 4.0,
                                                "IsRetention": true,
                                                "IsQuota": true,
                                                "TaxObject": "sample string 6"
                                            },
                                            {
                                                "Total": 1.0,
                                                "Name": "sample string 2",
                                                "Base": 3.0,
                                                "Rate": 4.0,
                                                "IsRetention": true,
                                                "IsQuota": true,
                                                "TaxObject": "sample string 6"
                                            }
                                            ],
                                            "Date": "sample string 5",
                                            "PaymentForm": "sample string 6",
                                            "Currency": "sample string 7",
                                            "ExchangeRate": 1.0,
                                            "Amount": 8.0,
                                            "OperationNumber": "sample string 9",
                                            "RfcIssuerPayerAccount": "sample string 10",
                                            "ForeignAccountNamePayer": "sample string 11",
                                            "PayerAccount": "sample string 12",
                                            "RfcReceiverBeneficiaryAccount": "sample string 13",
                                            "BeneficiaryAccount": "sample string 14",
                                            "ExpectedPaid": 2.0
                                        }
                                        ],
                                        "Donation": {
                                        "AuthorizationNumber": "sample string 1",
                                        "AuthorizationDate": "sample string 2",
                                        "Legend": "sample string 3"
                                        },
                                        "ForeignTrade": {
                                        "Issuer": {
                                            "Address": {
                                            "Street": "sample string 1",
                                            "ExteriorNumber": "sample string 2",
                                            "InteriorNumber": "sample string 3",
                                            "Neighborhood": "sample string 4",
                                            "Reference": "sample string 5",
                                            "ZipCode": "sample string 6"
                                            },
                                            "Curp": "sample string 1"
                                        },
                                        "Receiver": {
                                            "Address": {
                                            "Street": "sample string 1",
                                            "ExteriorNumber": "sample string 2",
                                            "InteriorNumber": "sample string 3",
                                            "Neighborhood": "sample string 4",
                                            "Reference": "sample string 5",
                                            "Locality": "sample string 6",
                                            "Municipality": "sample string 7",
                                            "State": "sample string 8",
                                            "Country": "sample string 9",
                                            "ZipCode": "sample string 10"
                                            }
                                        },
                                        "Owner": [
                                            {
                                            "NumRegIdTrib": "sample string 1",
                                            "TaxResidence": "sample string 2"
                                            },
                                            {
                                            "NumRegIdTrib": "sample string 1",
                                            "TaxResidence": "sample string 2"
                                            }
                                        ],
                                        "Recipient": [
                                            {
                                            "Name": "sample string 1",
                                            "NumRegIdTrib": "sample string 2",
                                            "Addresses": [
                                                {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Reference": "sample string 5",
                                                "Locality": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "ZipCode": "sample string 10"
                                                },
                                                {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Reference": "sample string 5",
                                                "Locality": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "ZipCode": "sample string 10"
                                                }
                                            ]
                                            },
                                            {
                                            "Name": "sample string 1",
                                            "NumRegIdTrib": "sample string 2",
                                            "Addresses": [
                                                {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Reference": "sample string 5",
                                                "Locality": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "ZipCode": "sample string 10"
                                                },
                                                {
                                                "Street": "sample string 1",
                                                "ExteriorNumber": "sample string 2",
                                                "InteriorNumber": "sample string 3",
                                                "Neighborhood": "sample string 4",
                                                "Reference": "sample string 5",
                                                "Locality": "sample string 6",
                                                "Municipality": "sample string 7",
                                                "State": "sample string 8",
                                                "Country": "sample string 9",
                                                "ZipCode": "sample string 10"
                                                }
                                            ]
                                            }
                                        ],
                                        "ReasonForTransfer": "sample string 1",
                                        "Commodity": [
                                            {
                                            "SpecificDescriptions": [
                                                {
                                                "Brand": "sample string 1",
                                                "Model": "sample string 2",
                                                "SubModel": "sample string 3",
                                                "SerialNumber": "sample string 4"
                                                },
                                                {
                                                "Brand": "sample string 1",
                                                "Model": "sample string 2",
                                                "SubModel": "sample string 3",
                                                "SerialNumber": "sample string 4"
                                                }
                                            ],
                                            "IdentificationNumber": "sample string 1",
                                            "TariffFraction": "sample string 2",
                                            "CustomsQuantity": 1.0,
                                            "CustomsUnit": "sample string 3",
                                            "CustomsUnitValue": 1.0,
                                            "ValueInDolar": 4.0
                                            },
                                            {
                                            "SpecificDescriptions": [
                                                {
                                                "Brand": "sample string 1",
                                                "Model": "sample string 2",
                                                "SubModel": "sample string 3",
                                                "SerialNumber": "sample string 4"
                                                },
                                                {
                                                "Brand": "sample string 1",
                                                "Model": "sample string 2",
                                                "SubModel": "sample string 3",
                                                "SerialNumber": "sample string 4"
                                                }
                                            ],
                                            "IdentificationNumber": "sample string 1",
                                            "TariffFraction": "sample string 2",
                                            "CustomsQuantity": 1.0,
                                            "CustomsUnit": "sample string 3",
                                            "CustomsUnitValue": 1.0,
                                            "ValueInDolar": 4.0
                                            }
                                        ],
                                        "RequestCode": "sample string 2",
                                        "Incoterm": "sample string 3",
                                        "ExchangeRateUSD": 1.0,
                                        "TotalUSD": 1.0,
                                        "OriginCertificate": true,
                                        "OriginCertificateNumber": "sample string 4",
                                        "ReliableExporterNumber": "sample string 5",
                                        "Observations": "sample string 6"
                                        },
                                        "Payroll": {
                                        "Issuer": {
                                            "EntitySNCF": {
                                            "OriginSource": "sample string 1",
                                            "AmountOriginSource": 1.0
                                            },
                                            "Curp": "sample string 1",
                                            "EmployerRegistration": "sample string 2",
                                            "FromEmployerRfc": "sample string 3"
                                        },
                                        "Employee": {
                                            "Outsourcing": [
                                            {
                                                "RfcContractor": "sample string 1",
                                                "PercentageTime": 2.0
                                            },
                                            {
                                                "RfcContractor": "sample string 1",
                                                "PercentageTime": 2.0
                                            }
                                            ],
                                            "Curp": "sample string 1",
                                            "SocialSecurityNumber": "sample string 2",
                                            "StartDateLaborRelations": "2025-08-26T11:35:25.3340413-06:00",
                                            "ContractType": "sample string 3",
                                            "Unionized": true,
                                            "TypeOfJourney": "sample string 4",
                                            "RegimeType": "sample string 5",
                                            "EmployeeNumber": "sample string 6",
                                            "Department": "sample string 7",
                                            "Position": "sample string 8",
                                            "PositionRisk": "sample string 9",
                                            "FrequencyPayment": "sample string 10",
                                            "Bank": "sample string 11",
                                            "BankAccount": "sample string 12",
                                            "BaseSalary": 1.0,
                                            "DailySalary": 1.0,
                                            "FederalEntityKey": "sample string 13"
                                        },
                                        "Perceptions": {
                                            "Details": [
                                            {
                                                "ActionsOrTitles": {
                                                "MarketValue": 1.0,
                                                "PriceWhenGranting": 2.0
                                                },
                                                "ExtraHours": [
                                                {
                                                    "Days": 1,
                                                    "HoursType": "sample string 2",
                                                    "ExtraHours": 3,
                                                    "PaidAmount": 4.0
                                                },
                                                {
                                                    "Days": 1,
                                                    "HoursType": "sample string 2",
                                                    "ExtraHours": 3,
                                                    "PaidAmount": 4.0
                                                }
                                                ],
                                                "PerceptionType": "sample string 1",
                                                "Code": "sample string 2",
                                                "Description": "sample string 3",
                                                "TaxedAmount": 4.0,
                                                "ExemptAmount": 5.0
                                            },
                                            {
                                                "ActionsOrTitles": {
                                                "MarketValue": 1.0,
                                                "PriceWhenGranting": 2.0
                                                },
                                                "ExtraHours": [
                                                {
                                                    "Days": 1,
                                                    "HoursType": "sample string 2",
                                                    "ExtraHours": 3,
                                                    "PaidAmount": 4.0
                                                },
                                                {
                                                    "Days": 1,
                                                    "HoursType": "sample string 2",
                                                    "ExtraHours": 3,
                                                    "PaidAmount": 4.0
                                                }
                                                ],
                                                "PerceptionType": "sample string 1",
                                                "Code": "sample string 2",
                                                "Description": "sample string 3",
                                                "TaxedAmount": 4.0,
                                                "ExemptAmount": 5.0
                                            }
                                            ],
                                            "Retirement": {
                                            "TotalASinglePayment": 1.0,
                                            "TotalParciality": 1.0,
                                            "DailyAmount": 1.0,
                                            "AccumulatedIncome": 1.0,
                                            "NonAccumulatedIncome": 2.0
                                            },
                                            "Indemnification": {
                                            "TotalPaid": 1.0,
                                            "YearsOfService": 2.0,
                                            "LastMonthlySalaryOrd": 3.0,
                                            "AccumulatedIncome": 4.0,
                                            "NonAccumulatedIncome": 5.0
                                            }
                                        },
                                        "Deductions": {
                                            "Details": [
                                            {
                                                "DeduccionType": "sample string 1",
                                                "Code": "sample string 2",
                                                "Description": "sample string 3",
                                                "Amount": 4.0
                                            },
                                            {
                                                "DeduccionType": "sample string 1",
                                                "Code": "sample string 2",
                                                "Description": "sample string 3",
                                                "Amount": 4.0
                                            }
                                            ]
                                        },
                                        "OtherPayments": [
                                            {
                                            "EmploymentSubsidy": {
                                                "Amount": 1.0
                                            },
                                            "Compensation": {
                                                "PositiveBalance": 1.0,
                                                "Year": 2,
                                                "RemainingPositiveBalance": 3.0
                                            },
                                            "OtherPaymentType": "sample string 1",
                                            "Code": "sample string 2",
                                            "Description": "sample string 3",
                                            "Amount": 4.0
                                            },
                                            {
                                            "EmploymentSubsidy": {
                                                "Amount": 1.0
                                            },
                                            "Compensation": {
                                                "PositiveBalance": 1.0,
                                                "Year": 2,
                                                "RemainingPositiveBalance": 3.0
                                            },
                                            "OtherPaymentType": "sample string 1",
                                            "Code": "sample string 2",
                                            "Description": "sample string 3",
                                            "Amount": 4.0
                                            }
                                        ],
                                        "Incapacities": [
                                            {
                                            "Days": 1,
                                            "Type": "sample string 2",
                                            "Amount": 1.0
                                            },
                                            {
                                            "Days": 1,
                                            "Type": "sample string 2",
                                            "Amount": 1.0
                                            }
                                        ],
                                        "Type": "sample string 1",
                                        "PaymentDate": "2025-08-26T11:35:25.3447644-06:00",
                                        "InitialPaymentDate": "2025-08-26T11:35:25.3447644-06:00",
                                        "FinalPaymentDate": "2025-08-26T11:35:25.3447644-06:00",
                                        "DaysPaid": 4.0
                                        },
                                        "TaxLegends": {
                                        "Legends": [
                                            {
                                            "TaxProvision": "sample string 1",
                                            "Norm": "sample string 2",
                                            "Text": "sample string 3"
                                            },
                                            {
                                            "TaxProvision": "sample string 1",
                                            "Norm": "sample string 2",
                                            "Text": "sample string 3"
                                            }
                                        ]
                                        },
                                        "CartaPorte31": {
                                        "RegimenesAduaneros": [
                                            {
                                            "RegimenAduanero": "sample string 1"
                                            },
                                            {
                                            "RegimenAduanero": "sample string 1"
                                            }
                                        ],
                                        "IdCCP": "sample string 1",
                                        "TranspInternac": "sample string 2",
                                        "EntradaSalidaMerc": "sample string 3",
                                        "PaisOrigenDestino": "sample string 4",
                                        "ViaEntradaSalida": "sample string 5",
                                        "TotalDistRec": 1.0,
                                        "RegistroISTMO": "sample string 6",
                                        "UbicacionPoloOrigen": "sample string 7",
                                        "UbicacionPoloDestino": "sample string 8",
                                        "Ubicaciones": [
                                            {
                                            "TranspInternac": 0,
                                            "Id": "sample string 1",
                                            "TiposTransporte": [
                                                0,
                                                0
                                            ],
                                            "Domicilio": {
                                                "Calle": "sample string 1",
                                                "NumeroExterior": "sample string 2",
                                                "NumeroInterior": "sample string 3",
                                                "Colonia": "sample string 4",
                                                "Localidad": "sample string 5",
                                                "Referencia": "sample string 6",
                                                "Municipio": "sample string 7",
                                                "MunicipioName": "sample string 8",
                                                "Estado": "sample string 9",
                                                "Pais": "sample string 10",
                                                "CodigoPostal": "sample string 11"
                                            },
                                            "TipoUbicacion": "sample string 2",
                                            "IDUbicacion": "sample string 3",
                                            "RFCRemitenteDestinatario": "sample string 4",
                                            "NombreRemitenteDestinatario": "sample string 5",
                                            "NumRegIdTrib": "sample string 6",
                                            "ResidenciaFiscal": "sample string 7",
                                            "NumEstacion": "sample string 8",
                                            "NombreEstacion": "sample string 9",
                                            "NavegacionTrafico": "sample string 10",
                                            "FechaHoraSalidaLlegada": "sample string 11",
                                            "TipoEstacion": "sample string 12",
                                            "DistanciaRecorrida": 13.0
                                            },
                                            {
                                            "TranspInternac": 0,
                                            "Id": "sample string 1",
                                            "TiposTransporte": [
                                                0,
                                                0
                                            ],
                                            "Domicilio": {
                                                "Calle": "sample string 1",
                                                "NumeroExterior": "sample string 2",
                                                "NumeroInterior": "sample string 3",
                                                "Colonia": "sample string 4",
                                                "Localidad": "sample string 5",
                                                "Referencia": "sample string 6",
                                                "Municipio": "sample string 7",
                                                "MunicipioName": "sample string 8",
                                                "Estado": "sample string 9",
                                                "Pais": "sample string 10",
                                                "CodigoPostal": "sample string 11"
                                            },
                                            "TipoUbicacion": "sample string 2",
                                            "IDUbicacion": "sample string 3",
                                            "RFCRemitenteDestinatario": "sample string 4",
                                            "NombreRemitenteDestinatario": "sample string 5",
                                            "NumRegIdTrib": "sample string 6",
                                            "ResidenciaFiscal": "sample string 7",
                                            "NumEstacion": "sample string 8",
                                            "NombreEstacion": "sample string 9",
                                            "NavegacionTrafico": "sample string 10",
                                            "FechaHoraSalidaLlegada": "sample string 11",
                                            "TipoEstacion": "sample string 12",
                                            "DistanciaRecorrida": 13.0
                                            }
                                        ],
                                        "Mercancias": {
                                            "LogisticaInversaRecoleccionDevolucion": "sample string 1",
                                            "Mercancia": [
                                            {
                                                "SectorCOFEPRIS": "sample string 1",
                                                "NombreIngredienteActivo": "sample string 2",
                                                "NomQuimico": "sample string 3",
                                                "DenominacionGenericaProd": "sample string 4",
                                                "DenominacionDistintivaProd": "sample string 5",
                                                "Fabricante": "sample string 6",
                                                "FechaCaducidad": "sample string 7",
                                                "LoteMedicamento": "sample string 8",
                                                "FormaFarmaceutica": "sample string 9",
                                                "CondicionesEspTransp": "sample string 10",
                                                "RegistroSanitarioFolioAutorizacion": "sample string 11",
                                                "PermisoImportacion": "sample string 12",
                                                "FolioImpoVUCEM": "sample string 13",
                                                "NumCAS": "sample string 14",
                                                "RazonSocialEmpImp": "sample string 15",
                                                "NumRegSanPlagCOFEPRIS": "sample string 16",
                                                "DatosFabricante": "sample string 17",
                                                "DatosFormulador": "sample string 18",
                                                "DatosMaquilador": "sample string 19",
                                                "UsoAutorizado": "sample string 20",
                                                "TipoMateria": "sample string 21",
                                                "DescripcionMateria": "sample string 22",
                                                "GuiasIdentificacion": [
                                                {
                                                    "NumeroGuiaIdentificacion": "sample string 1",
                                                    "DescripGuiaIdentificacion": "sample string 2",
                                                    "PesoGuiaIdentificacion": 3.0
                                                },
                                                {
                                                    "NumeroGuiaIdentificacion": "sample string 1",
                                                    "DescripGuiaIdentificacion": "sample string 2",
                                                    "PesoGuiaIdentificacion": 3.0
                                                }
                                                ],
                                                "CantidadTransporta": [
                                                {
                                                    "Cantidad": 1.0,
                                                    "IDOrigen": "sample string 2",
                                                    "IDDestino": "sample string 3",
                                                    "CvesTransporte": "sample string 4"
                                                },
                                                {
                                                    "Cantidad": 1.0,
                                                    "IDOrigen": "sample string 2",
                                                    "IDDestino": "sample string 3",
                                                    "CvesTransporte": "sample string 4"
                                                }
                                                ],
                                                "DocumentacionAduanera": [
                                                {
                                                    "TranspInternac": "sample string 1",
                                                    "EntradaSalidaMerc": "sample string 2",
                                                    "TipoDocumento": "sample string 3",
                                                    "NumPedimento": "sample string 4",
                                                    "IdentDocAduanero": "sample string 5",
                                                    "RFCImpo": "sample string 6"
                                                },
                                                {
                                                    "TranspInternac": "sample string 1",
                                                    "EntradaSalidaMerc": "sample string 2",
                                                    "TipoDocumento": "sample string 3",
                                                    "NumPedimento": "sample string 4",
                                                    "IdentDocAduanero": "sample string 5",
                                                    "RFCImpo": "sample string 6"
                                                }
                                                ],
                                                "DetalleMercancia": {
                                                "UnidadPesoMerc": "sample string 1",
                                                "PesoBruto": 2.0,
                                                "PesoNeto": 3.0,
                                                "PesoTara": 4.0,
                                                "NumPiezas": 5
                                                },
                                                "TiposTransporte": [
                                                0,
                                                0
                                                ],
                                                "TranspInternac": "sample string 23",
                                                "EntradaSalidaMerc": "sample string 24",
                                                "BienesTransp": "sample string 25",
                                                "ClaveSTCC": "sample string 26",
                                                "Descripcion": "sample string 27",
                                                "Cantidad": 28.0,
                                                "ClaveUnidad": "sample string 29",
                                                "Unidad": "sample string 30",
                                                "Dimensiones": "sample string 31",
                                                "MaterialPeligroso": "sample string 32",
                                                "CveMaterialPeligroso": "sample string 33",
                                                "Embalaje": "sample string 34",
                                                "DescripEmbalaje": "sample string 35",
                                                "PesoEnKg": 36.0,
                                                "ValorMercancia": 37.0,
                                                "Moneda": "sample string 38",
                                                "FraccionArancelaria": "sample string 39",
                                                "UUIDComercioExt": "sample string 40"
                                            },
                                            {
                                                "SectorCOFEPRIS": "sample string 1",
                                                "NombreIngredienteActivo": "sample string 2",
                                                "NomQuimico": "sample string 3",
                                                "DenominacionGenericaProd": "sample string 4",
                                                "DenominacionDistintivaProd": "sample string 5",
                                                "Fabricante": "sample string 6",
                                                "FechaCaducidad": "sample string 7",
                                                "LoteMedicamento": "sample string 8",
                                                "FormaFarmaceutica": "sample string 9",
                                                "CondicionesEspTransp": "sample string 10",
                                                "RegistroSanitarioFolioAutorizacion": "sample string 11",
                                                "PermisoImportacion": "sample string 12",
                                                "FolioImpoVUCEM": "sample string 13",
                                                "NumCAS": "sample string 14",
                                                "RazonSocialEmpImp": "sample string 15",
                                                "NumRegSanPlagCOFEPRIS": "sample string 16",
                                                "DatosFabricante": "sample string 17",
                                                "DatosFormulador": "sample string 18",
                                                "DatosMaquilador": "sample string 19",
                                                "UsoAutorizado": "sample string 20",
                                                "TipoMateria": "sample string 21",
                                                "DescripcionMateria": "sample string 22",
                                                "GuiasIdentificacion": [
                                                {
                                                    "NumeroGuiaIdentificacion": "sample string 1",
                                                    "DescripGuiaIdentificacion": "sample string 2",
                                                    "PesoGuiaIdentificacion": 3.0
                                                },
                                                {
                                                    "NumeroGuiaIdentificacion": "sample string 1",
                                                    "DescripGuiaIdentificacion": "sample string 2",
                                                    "PesoGuiaIdentificacion": 3.0
                                                }
                                                ],
                                                "CantidadTransporta": [
                                                {
                                                    "Cantidad": 1.0,
                                                    "IDOrigen": "sample string 2",
                                                    "IDDestino": "sample string 3",
                                                    "CvesTransporte": "sample string 4"
                                                },
                                                {
                                                    "Cantidad": 1.0,
                                                    "IDOrigen": "sample string 2",
                                                    "IDDestino": "sample string 3",
                                                    "CvesTransporte": "sample string 4"
                                                }
                                                ],
                                                "DocumentacionAduanera": [
                                                {
                                                    "TranspInternac": "sample string 1",
                                                    "EntradaSalidaMerc": "sample string 2",
                                                    "TipoDocumento": "sample string 3",
                                                    "NumPedimento": "sample string 4",
                                                    "IdentDocAduanero": "sample string 5",
                                                    "RFCImpo": "sample string 6"
                                                },
                                                {
                                                    "TranspInternac": "sample string 1",
                                                    "EntradaSalidaMerc": "sample string 2",
                                                    "TipoDocumento": "sample string 3",
                                                    "NumPedimento": "sample string 4",
                                                    "IdentDocAduanero": "sample string 5",
                                                    "RFCImpo": "sample string 6"
                                                }
                                                ],
                                                "DetalleMercancia": {
                                                "UnidadPesoMerc": "sample string 1",
                                                "PesoBruto": 2.0,
                                                "PesoNeto": 3.0,
                                                "PesoTara": 4.0,
                                                "NumPiezas": 5
                                                },
                                                "TiposTransporte": [
                                                0,
                                                0
                                                ],
                                                "TranspInternac": "sample string 23",
                                                "EntradaSalidaMerc": "sample string 24",
                                                "BienesTransp": "sample string 25",
                                                "ClaveSTCC": "sample string 26",
                                                "Descripcion": "sample string 27",
                                                "Cantidad": 28.0,
                                                "ClaveUnidad": "sample string 29",
                                                "Unidad": "sample string 30",
                                                "Dimensiones": "sample string 31",
                                                "MaterialPeligroso": "sample string 32",
                                                "CveMaterialPeligroso": "sample string 33",
                                                "Embalaje": "sample string 34",
                                                "DescripEmbalaje": "sample string 35",
                                                "PesoEnKg": 36.0,
                                                "ValorMercancia": 37.0,
                                                "Moneda": "sample string 38",
                                                "FraccionArancelaria": "sample string 39",
                                                "UUIDComercioExt": "sample string 40"
                                            }
                                            ],
                                            "Autotransporte": {
                                            "IdentificacionVehicular": {
                                                "ConfigVehicular": "sample string 1",
                                                "PlacaVM": "sample string 2",
                                                "AnioModeloVM": 3,
                                                "PesoBrutoVehicular": 4.0
                                            },
                                            "Remolques": [
                                                {
                                                "SubTipoRem": "sample string 1",
                                                "Placa": "sample string 2"
                                                },
                                                {
                                                "SubTipoRem": "sample string 1",
                                                "Placa": "sample string 2"
                                                }
                                            ],
                                            "PermSCT": "sample string 1",
                                            "NumPermisoSCT": "sample string 2",
                                            "Seguros": {
                                                "AseguraRespCivil": "sample string 1",
                                                "PolizaRespCivil": "sample string 2",
                                                "AseguraMedAmbiente": "sample string 3",
                                                "PolizaMedAmbiente": "sample string 4",
                                                "AseguraCarga": "sample string 5",
                                                "PolizaCarga": "sample string 6",
                                                "PrimaSeguro": 7.0
                                            }
                                            },
                                            "TransporteMaritimo": {
                                            "Puntal": 1.0,
                                            "PermisoTempNavegacion": "sample string 2",
                                            "Contenedor": [
                                                {
                                                "IdCCPRelacionado": "sample string 1",
                                                "PlacaVMCCP": "sample string 2",
                                                "FechaCertificacionCCP": "sample string 3",
                                                "RemolquesCCP": [
                                                    {
                                                    "SubTipoRemCCP": "sample string 1",
                                                    "PlacaCCP": "sample string 2"
                                                    },
                                                    {
                                                    "SubTipoRemCCP": "sample string 1",
                                                    "PlacaCCP": "sample string 2"
                                                    }
                                                ],
                                                "TipoContenedor": "sample string 4",
                                                "MatriculaContenedor": "sample string 5",
                                                "NumPrecinto": "sample string 6"
                                                },
                                                {
                                                "IdCCPRelacionado": "sample string 1",
                                                "PlacaVMCCP": "sample string 2",
                                                "FechaCertificacionCCP": "sample string 3",
                                                "RemolquesCCP": [
                                                    {
                                                    "SubTipoRemCCP": "sample string 1",
                                                    "PlacaCCP": "sample string 2"
                                                    },
                                                    {
                                                    "SubTipoRemCCP": "sample string 1",
                                                    "PlacaCCP": "sample string 2"
                                                    }
                                                ],
                                                "TipoContenedor": "sample string 4",
                                                "MatriculaContenedor": "sample string 5",
                                                "NumPrecinto": "sample string 6"
                                                }
                                            ],
                                            "RemolquesCCP": [
                                                {
                                                "SubTipoRemCCP": "sample string 1",
                                                "PlacaCCP": "sample string 2"
                                                },
                                                {
                                                "SubTipoRemCCP": "sample string 1",
                                                "PlacaCCP": "sample string 2"
                                                }
                                            ],
                                            "PermSCT": "sample string 3",
                                            "NumPermisoSCT": "sample string 4",
                                            "NombreAseg": "sample string 5",
                                            "NumPolizaSeguro": "sample string 6",
                                            "TipoEmbarcacion": "sample string 7",
                                            "Matricula": "sample string 8",
                                            "NumeroOMI": "sample string 9",
                                            "AnioEmbarcacion": 10,
                                            "NombreEmbarc": "sample string 11",
                                            "NacionalidadEmbarc": "sample string 12",
                                            "UnidadesDeArqBruto": 13.0,
                                            "TipoCarga": "sample string 14",
                                            "Eslora": 15.0,
                                            "Manga": 16.0,
                                            "Calado": 17.0,
                                            "LineaNaviera": "sample string 18",
                                            "NombreAgenteNaviero": "sample string 19",
                                            "NumAutorizacionNaviero": "sample string 20",
                                            "NumViaje": "sample string 21",
                                            "NumConocEmbarc": "sample string 22"
                                            },
                                            "TransporteAereo": {
                                            "PermSCT": "sample string 1",
                                            "NumPermisoSCT": "sample string 2",
                                            "MatriculaAeronave": "sample string 3",
                                            "NombreAseg": "sample string 4",
                                            "NumPolizaSeguro": "sample string 5",
                                            "NumeroGuia": "sample string 6",
                                            "LugarContrato": "sample string 7",
                                            "CodigoTransportista": "sample string 8",
                                            "RFCEmbarcador": "sample string 9",
                                            "NumRegIdTribEmbarc": "sample string 10",
                                            "ResidenciaFiscalEmbarc": "sample string 11",
                                            "NombreEmbarcador": "sample string 12"
                                            },
                                            "TransporteFerroviario": {
                                            "TipoDeServicio": "sample string 1",
                                            "TipoDeTrafico": "sample string 2",
                                            "NombreAseg": "sample string 3",
                                            "NumPolizaSeguro": "sample string 4",
                                            "DerechosDePaso": [
                                                {
                                                "TipoDerechoDePaso": "sample string 1",
                                                "KilometrajePagado": 2.0
                                                },
                                                {
                                                "TipoDerechoDePaso": "sample string 1",
                                                "KilometrajePagado": 2.0
                                                }
                                            ],
                                            "Carro": [
                                                {
                                                "TipoDeServicio": "sample string 1",
                                                "TipoCarro": "sample string 2",
                                                "MatriculaCarro": "sample string 3",
                                                "GuiaCarro": "sample string 4",
                                                "ToneladasNetasCarro": 5.0,
                                                "Contenedor": [
                                                    {
                                                    "TipoContenedor": "sample string 1",
                                                    "PesoContenedorVacio": 2.0,
                                                    "PesoNetoMercancia": 3.0
                                                    },
                                                    {
                                                    "TipoContenedor": "sample string 1",
                                                    "PesoContenedorVacio": 2.0,
                                                    "PesoNetoMercancia": 3.0
                                                    }
                                                ]
                                                },
                                                {
                                                "TipoDeServicio": "sample string 1",
                                                "TipoCarro": "sample string 2",
                                                "MatriculaCarro": "sample string 3",
                                                "GuiaCarro": "sample string 4",
                                                "ToneladasNetasCarro": 5.0,
                                                "Contenedor": [
                                                    {
                                                    "TipoContenedor": "sample string 1",
                                                    "PesoContenedorVacio": 2.0,
                                                    "PesoNetoMercancia": 3.0
                                                    },
                                                    {
                                                    "TipoContenedor": "sample string 1",
                                                    "PesoContenedorVacio": 2.0,
                                                    "PesoNetoMercancia": 3.0
                                                    }
                                                ]
                                                }
                                            ]
                                            },
                                            "PesoBrutoTotal": 72.0,
                                            "UnidadPeso": "sample string 3",
                                            "PesoNetoTotal": 10.0,
                                            "CargoPorTasacion": 5.0,
                                            "NumTotalMercancias": 2
                                        },
                                        "FiguraTransporte": [
                                            {
                                            "NombreFigura": "sample string 1",
                                            "PartesTransporte": [
                                                {
                                                "ParteTransporte": "sample string 1"
                                                },
                                                {
                                                "ParteTransporte": "sample string 1"
                                                }
                                            ],
                                            "TipoFigura": "sample string 2",
                                            "RFCFigura": "sample string 3",
                                            "NumLicencia": "sample string 4",
                                            "NumRegIdTribFigura": "sample string 5",
                                            "ResidenciaFiscalFigura": "sample string 6",
                                            "Domicilio": {
                                                "Calle": "sample string 1",
                                                "NumeroExterior": "sample string 2",
                                                "NumeroInterior": "sample string 3",
                                                "Colonia": "sample string 4",
                                                "Localidad": "sample string 5",
                                                "Referencia": "sample string 6",
                                                "Municipio": "sample string 7",
                                                "MunicipioName": "sample string 8",
                                                "Estado": "sample string 9",
                                                "Pais": "sample string 10",
                                                "CodigoPostal": "sample string 11"
                                            }
                                            },
                                            {
                                            "NombreFigura": "sample string 1",
                                            "PartesTransporte": [
                                                {
                                                "ParteTransporte": "sample string 1"
                                                },
                                                {
                                                "ParteTransporte": "sample string 1"
                                                }
                                            ],
                                            "TipoFigura": "sample string 2",
                                            "RFCFigura": "sample string 3",
                                            "NumLicencia": "sample string 4",
                                            "NumRegIdTribFigura": "sample string 5",
                                            "ResidenciaFiscalFigura": "sample string 6",
                                            "Domicilio": {
                                                "Calle": "sample string 1",
                                                "NumeroExterior": "sample string 2",
                                                "NumeroInterior": "sample string 3",
                                                "Colonia": "sample string 4",
                                                "Localidad": "sample string 5",
                                                "Referencia": "sample string 6",
                                                "Municipio": "sample string 7",
                                                "MunicipioName": "sample string 8",
                                                "Estado": "sample string 9",
                                                "Pais": "sample string 10",
                                                "CodigoPostal": "sample string 11"
                                            }
                                            }
                                        ]
                                        },
                                        "ValesDeDespensa": {
                                        "Conceptos": [
                                            {
                                            "Identificador": "sample string 1",
                                            "Fecha": "2025-08-26T11:35:25.3501519-06:00",
                                            "Rfc": "sample string 3",
                                            "Curp": "sample string 4",
                                            "Nombre": "sample string 5",
                                            "NumSeguridadSocial": "sample string 6",
                                            "Importe": 7.0
                                            },
                                            {
                                            "Identificador": "sample string 1",
                                            "Fecha": "2025-08-26T11:35:25.3501519-06:00",
                                            "Rfc": "sample string 3",
                                            "Curp": "sample string 4",
                                            "Nombre": "sample string 5",
                                            "NumSeguridadSocial": "sample string 6",
                                            "Importe": 7.0
                                            }
                                        ],
                                        "RegistroPatronal": "sample string 1",
                                        "NumeroDeCuenta": "sample string 2",
                                        "Total": 3.0
                                        }
                                    },
                                    "Observations": "sample string 14",
                                    "OrderNumber": "sample string 15",
                                    "PaymentBankName": "sample string 16",
                                    "IdTaxEntityBankAccounts": "sample string 17"
                                }
                            
                            El siguiente es un ejemplo de factura real, tomala como base para generar la factura:
                                {
                                    "CfdiType": "I",
                                    "ExpeditionPlace": "20160",
                                    "GlobalInformation": {
                                        "Months": "07",
                                        "Periodicity": "04",
                                        "Year": 2025
                                    },
                                    "Items": [
                                        {
                                        "Description": "Ventas mes de Julio",
                                        "ProductCode": "31162800",
                                        "Quantity": 1,
                                        "Subtotal": 8767.24,
                                        "TaxObject": "02",
                                        "Taxes": [
                                            {
                                            "Base": 8767.24,
                                            "IsFederalTax": true,
                                            "IsRetention": false,
                                            "Name": "IVA",
                                            "Rate": 0.16,
                                            "Total": 1402.76
                                            }
                                        ],
                                        "Total": 10170,
                                        "Unit": "Variedad",
                                        "UnitCode": "AS",
                                        "UnitPrice": 8767.24
                                        }
                                    ],
                                    "PaymentForm": "01",
                                    "PaymentMethod": "PUE",
                                    "Receiver": {
                                        "CfdiUse": "S01",
                                        "FiscalRegime": "616",
                                        "Name": "PUBLICO EN GENERAL",
                                        "Rfc": "XAXX010101000",
                                        "TaxZipCode": "20160"
                                    }
                                }

                    Devuelve SOLO un JSON con:
                    {
                    "servicio": "FACTURACION",
                    "funcion": "crear_factura"
                    "params": { ... }
                    }
                    """
                    max_tokens = 2500
                    temperature = 0.1
            if servicio == "WHATSAPP":
                if funcion == "respuesta_final":
                    """
                    Cargar prompt de respuesta final de whatsapp con datos especificos para que openai tenga mas claridad sobre la accion a ejecutar
                    """
                    prompt = """
                    Ejecuta la funcion con los paremtros necesarios para cumplir con este paso solicitado de acuerdo al historial del asistente.
                    Servicio que requieres:
                    - WHATSAPP:
                        respuesta_final: si ya tienes todo y debes responder al usuario.

                    Devuelve SOLO un JSON con:
                    {
                    "servicio": "WHATSAPP",
                    "funcion": "respuesta_final"
                    }
                    """
                    max_tokens = 50
                    temperature = 0.1
            messages = historial + [{"role": "user", "content": prompt}]
            respuesta = await preguntar_a_openai(messages, max_tokens, temperature)

            # Buscar cualquier objeto JSON en la respuesta
            match = re.search(r'(\{[\s\S]*\})', respuesta)
            if match:
                bloque = match.group(1)
                try:
                    return json.loads(bloque)
                except json.JSONDecodeError as e:
                    print("⚠️ JSON malformado:", e)
                    return None

        except json.JSONDecodeError as e:
            print("⚠️ JSON malformado:", e)
            return None


async def generar_respuesta_final(historial):
    """Genera la respuesta de WhatsApp con base en el historial"""
    prompt = """
    Con base en el historial, redacta una respuesta corta, amable y clara
    para enviar por WhatsApp al usuario. No repitas información técnica.
    """
    messages = historial + [{"role": "user", "content": prompt}]
    return await preguntar_a_openai(messages, max_tokens=250, temperature=0.3)
