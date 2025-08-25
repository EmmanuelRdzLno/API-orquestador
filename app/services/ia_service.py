import os
import json, re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def preguntar_a_openai(messages, max_tokens=200, temperature=0.2):
    """Consulta genérica a OpenAI con historial de mensajes"""
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d")
        system_prompt = {
            "role": "system",
            "content": (
                f"Eres un asistente de WhatsApp que puede orquestar múltiples servicios:\n"
                f"- FACTURACIÓN (consultar_facturas, descargar_documento, crear_factura)\n"
                f"- WHATSAPP (responder al usuario de forma humanizada)\n"
                f"- DOCUMENTO (procesar_archivo, generar_archivo)\n"
                f"La fecha actual es {fecha_actual}.\n"
                "Siempre analiza el historial y decide el siguiente paso a ejecutar.\n"
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
        consultar_facturas(params): Obtienes un JSON con los datos de factura/s, puedes filtrar con 1 o los varios parámetros
            parametros:
                type: issued/recived/payroll
                folioStart: inicio de folios
                folioEnd: final de folios
                rfc: rfc del receptor de la factura a consultar
                dateStart: fecha de inicio de la factura
                dateEnd: fecha final de la factura
                status: all/active/canceled/pending estado de la factura del CFDI
        descargar_documento(params): Obtienes el tipo de archivo (pdf o xml) con el id de la factura todos los parametros son obligatorios
            parametros:
                id: id de la factura
                format: pdf/xml tipo de formato
                type: issued/recived/payroll
        crear_factura(json): Funcion para generar factura, se requieren solo los parametros necesarios de acuerdo al regimen fiscal del receptor y del tipo de factura. IMPORTANTE! solicita toda la informacion al cliente: 1. Partidas de lo que se va a facturar, 2. Datos fiscales del receptor (considera las obligaciones fiscales del receptor para emitir correctamente la factura, impuestos a doc a sus obligaciones), 3. Tipo de factura, 4. Forma de pago, etc. 
            ejemplo parametros:
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
                        ]
                }
    - WHATSAPP:
        respuesta_final(params)

    Devuelve SOLO un JSON con:
    {
      "servicio": "...",
      "funcion": "...",
      "params": { ... }
    }

    Importante:
    - Usa FACTURACION si falta consultar o descargar facturas.
    - Usa WHATSAPP si ya tienes todo y debes responder al usuario.
    """
    messages = historial + [{"role": "user", "content": prompt}]
    respuesta = await preguntar_a_openai(messages, max_tokens=200)

    # Buscar cualquier objeto JSON en la respuesta
    match = re.search(r'(\{[\s\S]*\})', respuesta)
    if match:
        bloque = match.group(1)
        try:
            return json.loads(bloque)
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
    return await preguntar_a_openai(messages, max_tokens=150)
