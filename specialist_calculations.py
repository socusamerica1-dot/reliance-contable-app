"""
specialist_calculations.py
Módulos de Cálculo Acotados y Puentes de Análisis Pre-Contable v2.5
Proyecto: Reliance Contable IA v4.3 - Juicio Profesional Contable y Auditoría
Autor: Prof. Jorge Bastidas (Universidad de Los Andes, 2026)

Principio Rector: "La realidad existe, la tecnología asiste, la mente gobierna."
Estas funciones calculan puentes de análisis a partir de entradas fácticas confirmadas.
Devuelven importes analíticos bajo estado 'REVIEW_REQUIRED'; deliberadamente NO contabilizan
ni generan asientos automáticos sin la decisión y firma humana profesional explícita.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Tuple, Dict, Any, List, Optional

CENT = Decimal("0.01")


def _nonnegative(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} debe ser un número finito y no negativo.")


# =============================================================================
# 1. IMPUESTO DIFERIDO (NIC 12 / NIIF PARA LAS PYMES SECCIÓN 29)
# =============================================================================

@dataclass(frozen=True)
class TaxDifference:
    item_type: Literal["asset", "liability"]
    carrying_amount: Decimal
    tax_base: Decimal
    enacted_or_substantively_enacted_rate: Decimal
    evidence_ids: Tuple[str, ...]
    exceptions_reviewed: bool
    recovery_assessed: bool
    reversal_dtl_available: Decimal = Decimal("0")
    future_taxable_profit_forecast: Decimal = Decimal("0")
    tax_planning_opportunities: Decimal = Decimal("0")
    is_initial_goodwill_dtl: bool = False
    is_equal_initial_asset_liability: bool = False
    taxing_authority_same: bool = True
    taxable_entity_same: bool = True
    reversal_period_compatible: bool = True
    tax_character_compatible: bool = True
    potential_double_counting_detected: bool = False
    discounting_applied: bool = False  # NIC 12 ¶53 prohíbe taxativamente el descuento


def assess_deferred_tax(item: TaxDifference) -> Dict[str, Any]:
    """
    Cálculo preliminar del efecto impositivo diferido conforme a NIC 12 / Sección 29.
    Examina las fuentes de recuperación en orden lógico sin presuponer jerarquía normativa absoluta.
    Separa potential_tax_effect, recognisable_amount_proposed y posting_eligibility.
    Ante un bloqueo por violación normativa, recognisable_amount_proposed es None (null),
    posting_eligibility es BLOCKED, y se conserva el potential_tax_effect calculado válidamente.
    """
    _nonnegative(item.carrying_amount, "carrying_amount")
    _nonnegative(item.tax_base, "tax_base")
    _nonnegative(item.reversal_dtl_available, "reversal_dtl_available")
    _nonnegative(item.future_taxable_profit_forecast, "future_taxable_profit_forecast")
    _nonnegative(item.tax_planning_opportunities, "tax_planning_opportunities")
    
    rate = item.enacted_or_substantively_enacted_rate
    if not rate.is_finite() or not (Decimal("0") <= rate <= Decimal("1")):
        raise ValueError("La tasa impositiva debe estar expresada entre 0 y 1 (ej. 0.30 para 30%).")
    if not item.evidence_ids or not item.exceptions_reviewed:
        raise ValueError("Faltan identificadores de evidencia documental o confirmación de excepciones.")

    difference = (
        item.carrying_amount - item.tax_base
        if item.item_type == "asset"
        else item.tax_base - item.carrying_amount
    )
    potential_tax_effect = abs(difference) * rate

    diff_quant = difference.quantize(CENT, rounding=ROUND_HALF_UP)
    pot_tax_quant = potential_tax_effect.quantize(CENT, rounding=ROUND_HALF_UP)

    # Excepción 0: Prohibición expresa de descuento financiero (NIC 12 ¶53 / Sección 29 ¶29.28)
    if item.discounting_applied:
        return {
            "temporary_difference": diff_quant,
            "candidate_type": "PROHIBITED_DISCOUNTING",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": None,
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_DISCOUNTING_PROHIBITED",
            "status": "PROHIBITED_BY_STANDARD",
            "warning": (
                "VIOLACIÓN TAXATIVA NIC 12 ¶53: Los activos y pasivos por impuestos diferidos NO deben descontarse a valor presente. "
                "Cualquier rutina financiera que descuente estos saldos debe ser rechazada."
            ),
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 ¶53 / NIIF PYMES Sec. 29 ¶29.28",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Excepción 1: Reconocimiento inicial de plusvalía (NIC 12 ¶15a)
    if item.is_initial_goodwill_dtl:
        return {
            "temporary_difference": diff_quant,
            "candidate_type": "EXCLUDED_SCOPE_GOODWILL_DTL",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": None,
            "posting_eligibility": "BLOCKED",
            "proposed_action": "EXCLUDED_SCOPE_GOODWILL_DTL",
            "status": "PROHIBITED_BY_STANDARD",
            "warning": "NIC 12 ¶15(a) prohíbe taxativamente reconocer un pasivo por impuesto diferido surgido del reconocimiento inicial de la plusvalía (Goodwill).",
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 ¶15(a)",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Excepción 2: Alerta de doble cómputo de la misma ganancia fiscal
    if item.potential_double_counting_detected:
        return {
            "temporary_difference": diff_quant,
            "candidate_type": "DOUBLE_COUNTING_ERROR",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": None,
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_DOUBLE_COUNTING",
            "status": "BLOCKED_DOUBLE_COUNTING",
            "warning": (
                "ALERTA METODOLÓGICA NIC 12: Se detectó que la misma ganancia imponible futura fue computada simultáneamente "
                "en la reversión de DTL y en el pronóstico fiscal, inflando artificialmente el sustento de recuperación del DTA."
            ),
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 ¶28-29",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Incompatibilidad temporal / vencimiento legal de pérdidas fiscales (NIC 12 ¶34-36)
    if not item.reversal_period_compatible:
        return {
            "temporary_difference": diff_quant,
            "candidate_type": "DTA_TIMING_INCOMPATIBLE",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": None,
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_TIMING_INCOMPATIBILITY_NIC12_PAR34_36",
            "status": "BLOCKED_TIMING_INCOMPATIBILITY_NIC12_PAR34_36",
            "warning": (
                "ALERTA DE RECONOCIMIENTO NIC 12 ¶34–36: Pérdidas fiscales acumuladas con vencimiento legal "
                "no pueden respaldarse en ganancias fiscales proyectadas fuera del horizonte de caducidad tributaria. "
                "Se bloquea el reconocimiento del DTA por falta de ganancias imponibles oportunas durante el plazo legal de prescripción."
            ),
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 ¶34–36",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Incompatibilidad de jurisdicción o entidad: prohibición de compensación en presentación (NIC 12 ¶74)
    if not item.taxing_authority_same or not item.taxable_entity_same:
        return {
            "temporary_difference": diff_quant,
            "candidate_type": "INCOMPATIBLE_JURISDICTION_OR_ENTITY",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": None,
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_OFFSET_PROHIBITED",
            "status": "BLOCKED_OFFSET_PROHIBITED",
            "warning": (
                "ALERTA DE COMPENSACIÓN NIC 12 ¶74: No procede compensar activos por impuestos diferidos contra pasivos "
                "por impuestos diferidos pertenecientes a distintas autoridades tributarias o diferentes entidades sujetas a gravamen "
                "sin un derecho legalmente exigible de compensación."
            ),
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 ¶74",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Evaluación de recuperabilidad para activos por impuesto diferido (DTA)
    if difference < 0:
        total_recovery_base = (
            item.reversal_dtl_available
            + item.future_taxable_profit_forecast
            + item.tax_planning_opportunities
        )

        if not item.recovery_assessed and total_recovery_base == Decimal("0"):
            return {
                "temporary_difference": diff_quant,
                "candidate_type": "DTA_BLOCKED",
                "potential_tax_effect": pot_tax_quant,
                "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
                "recognisable_amount_proposed": None,
                "posting_eligibility": "BLOCKED",
                "proposed_action": "NO_RECOGNITION_SUPPORTED",
                "status": "BLOCKED_PENDING_RECOVERY_ASSESSMENT",
                "warning": (
                    "El activo por impuesto diferido NO puede proponerse para reconocimiento sin evaluación formal del orden "
                    "de fuentes de recuperación (NIC 12 ¶28-31: reversión de DTL existentes en la misma jurisdicción/entidad, "
                    "ganancias futuras proyectadas y planificación fiscal viable)."
                ),
                "evidence_ids": list(item.evidence_ids),
                "norma_referencia": "NIC 12 ¶24, ¶28-31 / Sección 29 ¶29.14",
                "rounding_policy": "ROUND_HALF_UP"
            }

        recognisable_base = min(abs(difference), total_recovery_base) if total_recovery_base > 0 else abs(difference)
        recognisable_amount = recognisable_base * rate
        rec_amt_quant = recognisable_amount.quantize(CENT, rounding=ROUND_HALF_UP)
        unrec_amt_quant = (pot_tax_quant - rec_amt_quant).quantize(CENT, rounding=ROUND_HALF_UP)
        is_partial = recognisable_base < abs(difference)

        return {
            "temporary_difference": diff_quant,
            "candidate_type": "DTA",
            "potential_tax_effect": pot_tax_quant,
            "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
            "recognisable_amount_proposed": rec_amt_quant,
            "recognisable_amount_proposed_formatted": f"{rec_amt_quant:,.2f} u.m.",
            "unrecognised_amount": unrec_amt_quant,
            "posting_eligibility": "ELIGIBLE_PENDING_REVIEW",
            "is_partial_recognition": is_partial,
            "proposed_action": "RECOGNISABLE_AMOUNT_PROPOSED",
            "status": "REVIEW_REQUIRED",
            "warning": (
                f"Propuesta de reconocimiento parcial: Solo {rec_amt_quant:,.2f} u.m. de {pot_tax_quant:,.2f} u.m. "
                f"están sustentados por fuentes de recuperación evaluadas en el orden de examen (NIC 12 ¶28-31). "
                f"El motor propone este importe; la decisión de reconocimiento permanece en la firma humana profesional."
                if is_partial else "DTA sustentado por fuentes de recuperación evaluadas. Propuesta sujeta a revisión y firma profesional."
            ),
            "evidence_ids": list(item.evidence_ids),
            "norma_referencia": "NIC 12 Impuesto a las Ganancias / Sección 29 NIIF PYMES",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # Caso pasivo por impuesto diferido (DTL)
    return {
        "temporary_difference": diff_quant,
        "candidate_type": "DTL" if difference > 0 else "NONE",
        "potential_tax_effect": pot_tax_quant,
        "potential_tax_effect_formatted": f"{pot_tax_quant:,.2f} u.m.",
        "recognisable_amount_proposed": pot_tax_quant,
        "recognisable_amount_proposed_formatted": f"{pot_tax_quant:,.2f} u.m.",
        "unrecognised_amount": Decimal("0.00"),
        "posting_eligibility": "ELIGIBLE_PENDING_REVIEW",
        "is_partial_recognition": False,
        "proposed_action": "RECOGNISABLE_AMOUNT_PROPOSED",
        "status": "REVIEW_REQUIRED",
        "warning": "DTL cuantificado preliminarmente. Requiere validación de la tasa aplicable en el período de liquidación.",
        "evidence_ids": list(item.evidence_ids),
        "norma_referencia": "NIC 12 Impuesto a las Ganancias / Sección 29 NIIF PYMES",
        "rounding_policy": "ROUND_HALF_UP"
    }


# =============================================================================
# 2. COMBINACIÓN DE NEGOCIOS & PUENTE PPA (NIIF 3 / NIIF PARA PYMES SECCIÓN 19)
# =============================================================================

@dataclass(frozen=True)
class AcquisitionBridge:
    consideration: Decimal
    non_controlling_interest: Decimal
    previously_held_interest: Decimal
    identifiable_assets_fv: Decimal
    assumed_liabilities_fv: Decimal
    business_confirmed: bool
    common_control_excluded: bool
    evidence_ids: Tuple[str, ...]
    pymes_edition: Literal["2015", "2025"] = "2025"
    initial_accounting_complete: bool = False
    months_since_acquisition: int = 0


def assess_acquisition_bridge(case: AcquisitionBridge) -> Dict[str, Any]:
    """
    Puente de asignación de precio de adquisición (PPA).
    Calcula la plusvalía (Goodwill) provisional o alerta sobre compra ventajosa (Bargain Purchase).
    """
    if not case.business_confirmed or not case.common_control_excluded:
        return {
            "status": "BLOCKED_SCOPE_ERROR",
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_SCOPE_ERROR",
            "error": "Confirme que la transacción califica como 'Negocio' (actividades + activos) y descarte entidades bajo control común antes de invocar NIIF 3 / Sec 19.",
            "provisional_goodwill": Decimal("0.00"),
            "potential_bargain_purchase": Decimal("0.00"),
            "rounding_policy": "ROUND_HALF_UP"
        }
    if not case.evidence_ids:
        raise ValueError("Falta evidencia documental de la adquisición y de los informes periciales de valoración.")
        
    for name in (
        "consideration", "non_controlling_interest",
        "previously_held_interest", "identifiable_assets_fv",
        "assumed_liabilities_fv"
    ):
        _nonnegative(getattr(case, name), name)

    net_assets = case.identifiable_assets_fv - case.assumed_liabilities_fv
    residual = (
        case.consideration
        + case.non_controlling_interest
        + case.previously_held_interest
        - net_assets
    )

    is_bargain = residual < 0
    
    if case.pymes_edition == "2025":
        goodwill_amort_par = "¶19.34 (Edición 2025)"
        bargain_par = "¶19.23 y ¶19.24 (Edición 2025, revisión previa obligatoria)"
    else:
        goodwill_amort_par = "¶19.23 (Edición 2015)"
        bargain_par = "¶19.24 (Edición 2015)"

    if is_bargain:
        ppa_status = "REASSESS_REQUIRED"
        warning_msg = (
            f"ALERTA NIIF 3 ¶36 y Sección 19 {bargain_par}: Antes de reconocer ganancia por compra ventajosa en resultados, "
            f"el auditor DEBE reevaluar exhaustivamente la identificación y medición de todos los activos adquiridos y pasivos asumidos."
        )
    elif case.initial_accounting_complete:
        ppa_status = "PPA_FINAL_DEFINITIVE"
        warning_msg = (
            f"PPA finalizado y definitivo: La contabilización inicial está completa antes del vencimiento del plazo anual. "
            f"El período de medición de 12 meses es un límite máximo, no una espera obligatoria (NIIF 3 ¶45). "
            f"En PYMES se amortiza sistemáticamente según {goodwill_amort_par}; en NIIF Plenas se somete a test de deterioro anual (NIC 36)."
        )
    elif case.months_since_acquisition > 12:
        ppa_status = "MEASUREMENT_PERIOD_EXPIRED_PPA_LOCKED"
        warning_msg = (
            f"El período de medición de 12 meses ha expirado (NIIF 3 ¶45). Los valores quedan bloqueados; "
            f"cualquier ajuste posterior no corregirá retrospectivamente la plusvalía sino que constituirá corrección de error bajo NIC 8."
        )
    else:
        ppa_status = "MEASUREMENT_PERIOD_PROVISIONAL_MAX_12M"
        warning_msg = (
            f"Plusvalía provisional sujeta al período de medición máximo de 12 meses (NIIF 3 ¶45). "
            f"Solo aplica provisionalidad a partidas cuya información sobre hechos existentes a la fecha de adquisición esté incompleta. "
            f"En NIIF Plenas no se amortiza; en PYMES se amortiza sistemáticamente según {goodwill_amort_par}."
        )

    net_assets_dec = net_assets.quantize(CENT, rounding=ROUND_HALF_UP)
    goodwill_dec = max(residual, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)
    bargain_dec = max(-residual, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "identifiable_net_assets": net_assets_dec,
        "identifiable_net_assets_formatted": f"{net_assets_dec:,.2f} u.m.",
        "provisional_goodwill": goodwill_dec,
        "provisional_goodwill_formatted": f"{goodwill_dec:,.2f} u.m.",
        "potential_bargain_purchase": bargain_dec,
        "potential_bargain_purchase_formatted": f"{bargain_dec:,.2f} u.m.",
        "posting_eligibility": "BLOCKED" if ppa_status.startswith("BLOCKED_") else ("REASSESS_REQUIRED" if is_bargain else "ELIGIBLE_PENDING_REVIEW"),
        "proposed_action": "REASSESS_REQUIRED" if is_bargain else "RECOGNISABLE_AMOUNT_PROPOSED",
        "status": ppa_status,
        "warning": warning_msg,
        "evidence_ids": list(case.evidence_ids),
        "norma_referencia": f"NIIF 3 Combinaciones de Negocios / Sección 19 NIIF PYMES ({case.pymes_edition})",
        "rounding_policy": "ROUND_HALF_UP"
    }


# =============================================================================
# 3. JERARQUÍA DE VALOR RAZONABLE (NIIF 13 / NIIF PARA PYMES SECCIÓN 12)
# =============================================================================

@dataclass(frozen=True)
class ValuationInput:
    level: Literal[1, 2, 3]
    significant: bool
    evidence_id: str


@dataclass(frozen=True)
class FairValueCase:
    amount_supplied: Decimal
    requiring_standard: str
    measurement_date_documented: bool
    market_participant_basis_documented: bool
    inputs: Tuple[ValuationInput, ...]
    measurement_recurrence: Literal["recurring", "non_recurring"] = "recurring"
    is_financial_instrument: bool = False
    active_market_quoted_price_adjusted: bool = False
    adjustment_is_observable: bool = False
    adjustment_is_significant: bool = True
    alternative_assumptions_change_fv_significantly: bool = False


def assess_fair_value(case: FairValueCase) -> Dict[str, Any]:
    """
    Clasifica el nivel de la jerarquía de valor razonable conforme a NIIF 13 ¶73-75.
    El nivel se determina a partir del insumo de menor nivel (menos observable) que sea SIGNIFICATIVO.
    """
    _nonnegative(case.amount_supplied, "amount_supplied")
    if not case.requiring_standard or case.requiring_standard.strip().upper() == "IFRS 13":
        raise ValueError("Identifique la norma primaria que requiere o permite esta medición (ej. NIIF 9, NIIF 16, NIC 40, NIC 38).")
    if not case.measurement_date_documented or not case.market_participant_basis_documented:
        raise ValueError("Faltan fecha de medición documentada o premisas verificadas de participantes de mercado.")
        
    significant = [item for item in case.inputs if item.significant]
    if not significant or any(not item.evidence_id for item in significant):
        raise ValueError("Documente cada insumo significativo y su soporte documental independiente.")

    highest_level_num = max(i.level for i in significant)
    
    # NIIF 13 ¶73-75: Reclasificación fundada en observabilidad y significatividad del ajuste
    if highest_level_num == 1 and case.active_market_quoted_price_adjusted:
        if case.adjustment_is_significant:
            if not case.adjustment_is_observable:
                highest_level_num = 3
            else:
                highest_level_num = 2

    level_descriptions = {
        1: "Nivel 1: Precios cotizados en mercados activos para activos o pasivos idénticos (sin ajustar).",
        2: "Nivel 2: Datos observables distintos de cotizaciones Nivel 1 (precios de activos similares, curvas de tasas observables).",
        3: "Nivel 3: Insumos no observables significativos basados en proyecciones internas."
    }

    amount_dec = case.amount_supplied.quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "hierarchy_level_candidate": highest_level_num,
        "hierarchy_description": level_descriptions.get(highest_level_num, ""),
        "amount_for_review": amount_dec,
        "amount_for_review_formatted": f"{amount_dec:,.2f} u.m.",
        "requiring_standard": case.requiring_standard,
        "posting_eligibility": "ELIGIBLE_PENDING_REVIEW",
        "proposed_action": "RECOGNISABLE_AMOUNT_PROPOSED",
        "status": "REVIEW_REQUIRED",
        "evidence_ids": [i.evidence_id for i in significant],
        "norma_referencia": "NIIF 13 Medición del Valor Razonable / Sección 12 NIIF PYMES",
        "rounding_policy": "ROUND_HALF_UP"
    }


# =============================================================================
# 4. DETERIORO DE VALOR POR UGE (NIC 36 / NIIF PARA LAS PYMES SECCIÓN 27)
# =============================================================================

@dataclass(frozen=True)
class CGUImpairmentCase:
    cgu_id: str
    carrying_amount: Decimal
    allocated_goodwill: Decimal
    fair_value_less_costs: Decimal
    value_in_use: Decimal
    evidence_ids: Tuple[str, ...]
    is_pymes: bool = False
    pymes_edition: Literal["2015", "2025"] = "2025"
    cgu_aggregation_independent: bool = True
    uncommitted_restructuring_or_enhancements_included: bool = False
    rate_and_cash_flows_currency_consistent: bool = True
    adversarial_reversal_attempted: bool = False


def assess_cgu_impairment(case: CGUImpairmentCase) -> Dict[str, Any]:
    """
    Cálculo preliminar del deterioro de valor por Unidad Generadora de Efectivo (NIC 36).
    Aplica la prelación de absorción: primero contra plusvalía (NIC 36 ¶104).
    Defiende activamente la prohibición de reversión de plusvalía (NIC 36 ¶124).
    """
    _nonnegative(case.carrying_amount, "carrying_amount")
    _nonnegative(case.allocated_goodwill, "allocated_goodwill")
    _nonnegative(case.fair_value_less_costs, "fair_value_less_costs")
    _nonnegative(case.value_in_use, "value_in_use")

    if not case.cgu_id or not case.evidence_ids:
        raise ValueError("Identifique formalmente la UGE y los expedientes de soporte pericial.")

    # 1. Chequeo de agregación indebida (NIC 36 ¶68)
    if not case.cgu_aggregation_independent:
        return {
            "status": "BLOCKED_AGGREGATION_VIOLATION",
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_AGGREGATION_VIOLATION",
            "warning": (
                "VIOLACIÓN NIC 36 ¶68: Se detectó agregación indebida de unidades que generan entradas de efectivo "
                "en gran medida independientes en una sola 'UGE Nacional', orientada a enmascarar el deterioro individual."
            ),
            "potential_impairment": Decimal("0.00"),
            "potential_impairment_formatted": "0.00 u.m.",
            "evidence_ids": list(case.evidence_ids),
            "norma_referencia": "NIC 36 ¶68",
            "rounding_policy": "ROUND_HALF_UP"
        }

    # 2. Chequeo de defensa contra intento adversarial de revertir deterioro de plusvalía (NIC 36 ¶124)
    if case.adversarial_reversal_attempted:
        return {
            "status": "BLOCKED_REVERSAL_PROHIBITED_NIC36_PAR124",
            "posting_eligibility": "BLOCKED",
            "proposed_action": "BLOCKED_REVERSAL_PROHIBITED_NIC36_PAR124",
            "warning": (
                "MANIPULACIÓN ADVERSARIAL RECHAZADA: NIC 36 ¶124 prohíbe taxativa y absolutamente revertir cualquier pérdida "
                "por deterioro reconocida sobre la plusvalía (Goodwill) en un período posterior."
            ),
            "potential_impairment": Decimal("0.00"),
            "potential_impairment_formatted": "0.00 u.m.",
            "evidence_ids": list(case.evidence_ids),
            "norma_referencia": "NIC 36 ¶124",
            "rounding_policy": "ROUND_HALF_UP"
        }

    total_carrying = case.carrying_amount + case.allocated_goodwill
    recoverable_amount = max(case.fair_value_less_costs, case.value_in_use)
    potential_impairment = max(total_carrying - recoverable_amount, Decimal("0"))

    # Prelación de distribución (NIC 36 ¶104): primero plusvalía
    loss_to_goodwill = min(potential_impairment, case.allocated_goodwill)
    loss_to_other_assets = potential_impairment - loss_to_goodwill

    has_impairment = potential_impairment > Decimal("0")

    total_carrying_dec = total_carrying.quantize(CENT, rounding=ROUND_HALF_UP)
    recoverable_dec = recoverable_amount.quantize(CENT, rounding=ROUND_HALF_UP)
    impairment_dec = potential_impairment.quantize(CENT, rounding=ROUND_HALF_UP)
    loss_gw_dec = loss_to_goodwill.quantize(CENT, rounding=ROUND_HALF_UP)
    loss_other_dec = loss_to_other_assets.quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "cgu_id": case.cgu_id,
        "total_carrying_amount": total_carrying_dec,
        "total_carrying_amount_formatted": f"{total_carrying_dec:,.2f} u.m.",
        "recoverable_amount": recoverable_dec,
        "recoverable_amount_formatted": f"{recoverable_dec:,.2f} u.m.",
        "recoverable_basis": "Valor en uso" if case.value_in_use >= case.fair_value_less_costs else "Valor razonable menos costos de disposición",
        "potential_impairment": impairment_dec,
        "potential_impairment_formatted": f"{impairment_dec:,.2f} u.m.",
        "loss_allocated_to_goodwill": loss_gw_dec,
        "loss_allocated_to_goodwill_formatted": f"{loss_gw_dec:,.2f} u.m.",
        "loss_allocated_to_other_assets": loss_other_dec,
        "loss_allocated_to_other_assets_formatted": f"{loss_other_dec:,.2f} u.m.",
        "posting_eligibility": "ELIGIBLE_PENDING_REVIEW" if has_impairment else "NO_IMPAIRMENT",
        "proposed_action": "RECOGNISABLE_AMOUNT_PROPOSED" if has_impairment else "NO_ACTION_REQUIRED",
        "status": "REVIEW_REQUIRED",
        "evidence_ids": list(case.evidence_ids),
        "norma_referencia": "NIC 36 Deterioro del Valor de los Activos / Sección 27 NIIF PYMES",
        "rounding_policy": "ROUND_HALF_UP"
    }
