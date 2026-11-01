"""Резолютивная часть военной ипотеки: отдельные требования банка и ЦЖЗ."""

from copy import deepcopy
from decimal import Decimal
import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from mortgage_awards import _money

FLAGS = {
    "bank_termination": "mortgageAwardTermination", "bank_debt": "mortgageAwardDebt",
    "bank_foreclosure": "mortgageAwardForeclosure",
    "czz_termination": "militaryAwardCzzTermination", "czz_debt": "militaryAwardCzzDebt",
    "czz_future": "militaryAwardCzzFutureInterest", "czz_foreclosure": "militaryAwardCzzForeclosure",
}
AMOUNTS = {
    "principal": ("mortgageAwardPrincipal", ("principalDebt", "loanDebt", "principalDebt13")),
    "interest": ("mortgageAwardInterest", ("interest", "interest14")),
    "penalty": ("mortgageAwardPenalty", ("forfeit", "forfeit15")),
    "interest_penalty": ("mortgageAwardInterestPenalty", ("forfeitInterest1362",)),
    "duty": ("mortgageAwardDuty", ("stateDuty16", "stateDuty")),
    "czz_principal": ("militaryAwardCzzPrincipal", ("milPrincipalCzz",)),
    "czz_interest": ("militaryAwardCzzInterest", ("milLoanInterest",)),
    "czz_penalty": ("militaryAwardCzzPenalty", ("milPenaltySum",)),
    "budget_duty": ("militaryAwardBudgetDuty", ("stateDutyLocalBudget1363",)),
}


def selection(data):
    """Частичные суммы не переносятся в исходные финансовые данные."""
    fields = data.get("fields") or {}
    def pick(key, default=""):
        return data[key] if key in data else fields.get(key, default)
    outcome = str(pick("claimResolution")).strip().lower()
    if outcome not in ("full", "partial", "deny"):
        raise ValueError("Выберите исход удовлетворения иска")
    partial = outcome == "partial"
    flags = {}
    for name, key in FLAGS.items():
        value = str(pick(key, "true")) if partial else ("false" if outcome == "deny" else "true")
        if value not in ("true", "false"):
            raise ValueError(f"Некорректный выбор требования: {key}")
        flags[name] = value == "true"
    amounts = {}
    for name, (key, aliases) in AMOUNTS.items():
        sources = (key, *aliases) if partial else aliases
        raw = next((pick(k) for k in sources if k in data or k in fields), "")
        active = name in ("duty", "budget_duty") or flags["czz_debt" if name.startswith("czz_") else "bank_debt"]
        amounts[name] = _money(raw) if active and outcome != "deny" else Decimal("0")
    if partial:
        if not any(flags.values()):
            raise ValueError("Все требования отклонены. Выберите «Отказать в удовлетворении»")
        for group, names in (("bank", ("principal", "interest", "penalty", "interest_penalty")),
                             ("czz", ("czz_principal", "czz_interest", "czz_penalty"))):
            if flags[f"{group}_debt"] and sum(amounts[n] for n in names) <= 0:
                raise ValueError("Укажите положительную присуждённую задолженность или снимите требование взыскания")
    return outcome, flags, amounts


def _block(doc, name):
    body = doc.element.body
    starts = [n for n in body.iter(qn("w:bookmarkStart")) if n.get(qn("w:name")) == name]
    if len(starts) != 1:
        raise ValueError(f"В военной резолютивке нужна одна закладка {name}")
    start = starts[0]
    ends = [n for n in body.iter(qn("w:bookmarkEnd")) if n.get(qn("w:id")) == start.get(qn("w:id"))]
    if len(ends) != 1:
        raise ValueError(f"Не найдена граница {name}")
    first, last = start.getparent(), ends[0].getparent()
    children = list(body)
    if first.getparent() is not body or last.getparent() is not body:
        raise ValueError(f"{name} должна охватывать целые абзацы")
    left, right = children.index(first), children.index(last)
    if left > right:
        raise ValueError(f"Перепутаны границы {name}")
    block = children[left:right + 1]
    if any(n.tag != qn("w:p") for n in block):
        raise ValueError(f"{name} может содержать только абзацы")
    for paragraph, boundary, before in ((first, start, True), (last, ends[0], False)):
        nodes = list(paragraph.iter())
        outside = nodes[:nodes.index(boundary)] if before else nodes[nodes.index(boundary) + 1:]
        if any(n.tag == qn("w:t") and (n.text or "").strip() for n in outside):
            raise ValueError(f"{name} должна охватывать абзацы полностью")
    return block


def _replace_block(doc, block, lines):
    prototype = block[0]
    for line in lines:
        node = OxmlElement("w:p")
        if prototype.pPr is not None:
            node.append(deepcopy(prototype.pPr))
        paragraph = Paragraph(node, doc._body)
        run = paragraph.add_run(line)
        old_runs = list(prototype.iter(qn("w:rPr")))
        if old_runs:
            run._r.insert(0, deepcopy(old_runs[0]))
        prototype.addprevious(node)
    for node in block:
        node.getparent().remove(node)


def render_military_decision(doc, data, generator):
    """Заполняет размеченные блоки, сохраняя оформление остального шаблона."""
    outcome, flags, amounts = selection(data)
    header = _block(doc, "MilitaryMortgageHeader")
    awards = _block(doc, "MilitaryMortgageAwards")
    if set(header) & set(awards):
        raise ValueError("Пересекаются закладки военной резолютивки")
    fields = data.get("fields") or {}
    def pick(*keys):
        for key in keys:
            value = data[key] if key in data else fields.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return "******"
    def date(*keys):
        return generator._normalize_date_format(pick(*keys))
    def money(value):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " руб."
    def rate(key):
        value = pick(key)
        if value != "******":
            value = format(_money(value), "f").replace(".", ",")
        return value + "%"
    debtors = data.get("debtors") or fields.get("debtors") or []
    debtors = [d for d in debtors if isinstance(d, dict) and str(d.get("name") or "").strip()]
    if not debtors:
        debtors = [{"name": pick("mortgageDebtorName", "debtorName", "applicantName"),
                    "birthDate": pick("birthDate"), "inn": pick("inn")}]
    def names(case, details=False):
        result = []
        for debtor in debtors:
            name = generator._decline_person_name(debtor["name"], case)
            if details:
                birth = generator._normalize_date_format(str(debtor.get("birthDate") or "******"))
                name += f" ({birth} года рождения, ИНН {debtor.get('inn') or '******'})"
            result.append(name)
        return ", ".join(result)
    bank = pick("creditorName")
    if re.search(r"росвоенипотек|накопительно-ипотечн", bank, re.I):
        raise ValueError("В поле истца укажите банк; взыскатель ЦЖЗ заполняется отдельно")
    bank_requisites = [f"{label} {pick(key)}" for key, label in
                       (("creditorInn", "ИНН"), ("creditorOgrn", "ОГРН")) if pick(key) != "******"]
    bank_recipient = bank + (" (" + ", ".join(bank_requisites) + ")" if bank_requisites else "")
    czz = pick("cjzClaimant1381")
    if czz == "******":
        czz = next((str(p.get("name")) for p in (data.get("thirdParties") or [])
                    if isinstance(p, dict) and re.search(r"росвоенипотек|накопительно-ипотечн", str(p.get("name")), re.I)),
                   "ФГКУ «Росвоенипотека»")
    extra = []
    for person in data.get("thirdParties") or fields.get("thirdParties") or []:
        name = str(person.get("name") or "").strip() if isinstance(person, dict) else ""
        if name and name not in extra and name != bank and not re.search(r"росвоенипотек|накопительно-ипотечн", name, re.I):
            extra.append(name)
    header_lines = [
        f"рассмотрев в открытом судебном заседании гражданское дело по иску {bank} к {names('datv')} о расторжении кредитного договора, взыскании задолженности, судебных расходов и обращении взыскания на заложенное имущество,",
        f"по самостоятельным требованиям {czz} к {names('datv')} о расторжении договора целевого жилищного займа, взыскании задолженности и обращении взыскания на заложенное имущество."
        + (f" Иные третьи лица: {', '.join(extra)}." if extra else ""),
    ]
    solidarity = "солидарно " if str(data.get("solidaryLiability") or fields.get("solidaryLiability")).lower() == "true" and len(debtors) > 1 else ""
    debtor_from = names("gent", True)
    lines = []
    if outcome == "deny":
        lines = [f"В удовлетворении исковых требований {bank} к {names('datv')} отказать.",
                 f"В удовлетворении самостоятельных требований {czz} к {names('datv')} отказать."]
    else:
        original_data = dict(data, claimResolution="full")
        _, _, original_amounts = selection(original_data)
        partial_parties = []
        for party, group, amount_names in (
            (bank, "bank", ("principal", "interest", "penalty", "interest_penalty", "duty")),
            (czz, "czz", ("czz_principal", "czz_interest", "czz_penalty")),
        ):
            group_flags = [enabled for key, enabled in flags.items() if key.startswith(group + "_")]
            has_award = any(group_flags) or (group == "bank" and amounts["duty"] > 0)
            if not has_award:
                lines.append(f"В удовлетворении требований {party} к {names('datv')} отказать.")
                continue
            complete = all(group_flags) and all(amounts[key] == original_amounts[key] for key in amount_names)
            suffix = "удовлетворить" if complete else "удовлетворить частично"
            lines.append(f"Требования {party} к {names('datv')} {suffix}.")
            if not complete:
                partial_parties.append(party)
        if flags["czz_termination"]:
            lines.append(f"Расторгнуть договор целевого жилищного займа № {pick('milCzzContractNumber')} от {date('milCzzContractDate')}, заключённый между {czz} и {names('ablt')}.")
        if flags["czz_debt"]:
            clauses = [(amounts["czz_principal"], "задолженность по ЦЖЗ (первоначальный взнос и платежи по кредиту)"),
                       (amounts["czz_interest"], f"проценты за период с {date('milInterestPeriodFrom')} по {date('milInterestPeriodTo')} по ставке {rate('milInterestRate')} годовых"),
                       (amounts["czz_penalty"], f"пени по ставке {rate('milPenaltyRate')} за каждый день просрочки")]
            total = sum(value for value, _ in clauses)
            lines.append(f"Взыскать {solidarity}с {debtor_from} в пользу {czz} денежные средства в размере {money(total)}, в том числе: "
                         + "; ".join(f"{money(value)} — {label}" for value, label in clauses if value) + ".")
        if flags["czz_future"]:
            lines.append(f"Взыскать {solidarity}с {debtor_from} в пользу {czz} проценты за пользование целевым жилищным займом по ставке {rate('milInterestRate')} годовых, начисляемые на сумму задолженности {money(amounts['czz_principal'] if flags['czz_debt'] else _money(pick('milPrincipalCzz').replace('******','0')))}, начиная с {date('milFutureInterestFrom')} по день вступления решения суда в законную силу включительно.")
        if flags["bank_termination"]:
            lines.append(f"Расторгнуть кредитный договор № {pick('creditContractNumber', 'contractNumber')} от {date('creditContractDate', 'contractDate')}, заключённый между {bank} и {names('ablt')}.")
        bank_total = sum(amounts[n] for n in ("principal", "interest", "penalty", "interest_penalty"))
        if flags["bank_debt"] or amounts["duty"]:
            text = f"Взыскать {solidarity}с {debtor_from} в пользу {bank_recipient} "
            if flags["bank_debt"]:
                parts = [(amounts["principal"], "просроченный основной долг"), (amounts["interest"], "просроченные проценты"),
                         (amounts["penalty"], "неустойка за просроченный основной долг"), (amounts["interest_penalty"], "неустойка за просроченные проценты")]
                text += f"задолженность по кредитному договору № {pick('creditContractNumber', 'contractNumber')} от {date('creditContractDate', 'contractDate')} за период с {date('creditPeriodFrom', 'mortgagePeriodStart120')} по {date('creditPeriodTo', 'mortgagePeriodEnd121')} (включительно) в размере {money(bank_total)}, в том числе: "
                text += "; ".join(f"{money(value)} — {label}" for value, label in parts if value)
                if amounts["duty"]:
                    text += ", а также "
            if amounts["duty"]:
                text += f"расходы по оплате государственной пошлины в размере {money(amounts['duty'])}"
            text += f", всего {money((bank_total if flags['bank_debt'] else 0) + amounts['duty'])}."
            lines.append(text)
        foreclosures = [who for enabled, who in ((flags["bank_foreclosure"], bank), (flags["czz_foreclosure"], czz)) if enabled]
        if foreclosures:
            properties = data.get("mortgageProperties") or fields.get("mortgageProperties") or []
            if not isinstance(properties, list) or any(not isinstance(p, dict) for p in properties):
                raise ValueError("Для обращения взыскания нужен список объектов недвижимости")
            properties = [p for p in properties if any(str(v or "").strip() for v in p.values())]
            if not properties:
                raise ValueError("Заполните хотя бы один предмет ипотеки")
            lines.append(f"Обратить взыскание в пользу {', '.join(foreclosures)} на следующее заложенное имущество путём продажи с публичных торгов:")
            for prop in properties:
                def prop_value(key):
                    return str(prop.get(key) or "******")
                price = prop.get("startingPrice")
                price_text = money(_money(price)) if str(price or "").strip() else "******"
                area = prop.get("area")
                if not area:
                    match = re.search(r"площад[ьи][^\d]{0,12}([\d]+[.,]?\d*)", prop_value("description"), re.I)
                    area = match.group(1) if match else "******"
                lines.extend([f"Объект недвижимости: {prop_value('description')}.",
                              f"Адрес: {prop_value('address')}. Общая площадь (кв. м.): {area}. Кадастровый номер: {prop_value('cadastralNumber')}.",
                              f"Начальная продажная стоимость: {price_text}."])
            if flags["bank_foreclosure"] and flags["czz_foreclosure"]:
                lines.append(f"Требования залогодержателя {czz} удовлетворяются после удовлетворения требований залогодержателя {bank}.")
        if amounts["budget_duty"]:
            lines.append(f"Взыскать с {debtor_from} в доход местного бюджета государственную пошлину в размере {money(amounts['budget_duty'])}.")
        if outcome == "partial":
            for party in partial_parties:
                lines.append(f"В удовлетворении остальной части требований {party} отказать.")
    _replace_block(doc, header, header_lines)
    lines = [line.replace("руб..", "руб.") for line in lines]
    _replace_block(doc, awards, lines)
    values = {
        "1": pick("caseNumber"), "7": date("courtDecisionDate", "date"),
        "0": pick("courtName"), "1307": pick("actCity1307"),
        "415": generator._decline_person_name(pick("judgeFullName", "judge"), "gent"),
        "29": generator._decline_person_name(pick("authorName", "secretaryFullName", "secretary"), "loct"),
        "1302": pick("higherCourt", "courtAppealName1302"),
    }
    if values["1307"] == "******":
        values["1307"] = generator._city_from_court_name(pick("courtName")) or "******"
    generator._apply_official_name_cases(doc, dict(data))
    for marker, value in values.items():
        generator._replace_placeholder_in_doc(doc, f"[{marker}]", value)
    for node in list(doc.element.iter(qn("w:bookmarkStart"))) + list(doc.element.iter(qn("w:bookmarkEnd"))):
        node.getparent().remove(node)
