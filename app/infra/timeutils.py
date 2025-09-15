"""
Utilitários de tempo para timezone brasileiro
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

# Timezone do Brasil (UTC-3)
TIMEZONE_BRASIL = timezone(timedelta(hours=-3))


def agora_br() -> datetime:
    """Retorna datetime atual no timezone brasileiro"""
    return datetime.now(TIMEZONE_BRASIL)


def agora_br_iso() -> str:
    """Retorna timestamp atual em formato ISO no timezone brasileiro"""
    return agora_br().isoformat()


def parsear_data_br(data_str: str) -> Optional[datetime]:
    """
    Tenta parsear string de data para datetime no timezone brasileiro
    Suporta vários formatos comuns
    """
    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ]
    
    for formato in formatos:
        try:
            dt = datetime.strptime(data_str, formato)
            # Assumir timezone brasileiro se não especificado
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
            return dt
        except ValueError:
            continue
    
    return None


def formatar_data_br(dt: datetime, formato: str = "%d/%m/%Y %H:%M") -> str:
    """Formata datetime para string no formato brasileiro"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    else:
        dt = dt.astimezone(TIMEZONE_BRASIL)
    
    return dt.strftime(formato)


def data_para_string_amigavel(dt: datetime) -> str:
    """Converte datetime para string amigável em português"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    else:
        dt = dt.astimezone(TIMEZONE_BRASIL)
    
    agora = agora_br()
    diff = agora - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return "agora"
        elif diff.seconds < 3600:
            minutos = diff.seconds // 60
            return f"há {minutos} minuto{'s' if minutos != 1 else ''}"
        else:
            horas = diff.seconds // 3600
            return f"há {horas} hora{'s' if horas != 1 else ''}"
    elif diff.days == 1:
        return "ontem"
    elif diff.days < 7:
        return f"há {diff.days} dias"
    else:
        return formatar_data_br(dt, "%d/%m/%Y")


def timestamp_para_datetime(timestamp: float) -> datetime:
    """Converte timestamp Unix para datetime no timezone brasileiro"""
    dt_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt_utc.astimezone(TIMEZONE_BRASIL)


def datetime_para_timestamp(dt: datetime) -> float:
    """Converte datetime para timestamp Unix"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    
    return dt.timestamp()


def validar_horario_comercial(dt: Optional[datetime] = None) -> bool:
    """Verifica se é horário comercial (7h às 22h, seg-dom)"""
    if dt is None:
        dt = agora_br()
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    else:
        dt = dt.astimezone(TIMEZONE_BRASIL)
    
    # Horário comercial: 7h às 22h
    return 7 <= dt.hour <= 22


def obter_inicio_dia(dt: Optional[datetime] = None) -> datetime:
    """Retorna início do dia (00:00) para a data especificada"""
    if dt is None:
        dt = agora_br()
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    else:
        dt = dt.astimezone(TIMEZONE_BRASIL)
    
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def obter_fim_dia(dt: Optional[datetime] = None) -> datetime:
    """Retorna fim do dia (23:59:59) para a data especificada"""
    if dt is None:
        dt = agora_br()
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE_BRASIL)
    else:
        dt = dt.astimezone(TIMEZONE_BRASIL)
    
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
