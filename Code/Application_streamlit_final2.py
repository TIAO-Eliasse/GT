import streamlit as st
import zipfile
import os
import pandas as pd
import re

import io

import plotly.express as px
from datetime import datetime


st.set_page_config(page_title="Dashboard", layout="wide")

st.markdown("""
<style>
/* === STRUCTURE GLOBALE === */
body, .main, .block-container {
    margin: 0 !important;
    padding-top: 0rem !important;
    background-color: #f4f6f8 !important; /* gris clair bleuté */
    color: #2c3e100;
    font-family: 'Segoe UI', sans-serif;
}

/* === HEADER TRANSPARENT === */
[data-testid="stHeader"] {
    background-color: rgba(0, 0, 0, 0);
    height: 0px !important;
    padding: 0 !important;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background-color: #eaf2f8 !important;  /* bleu doux */
    color: #1104360;
}

/* === TITRES === */
h1, h2, h3, h4, h10, h6 {
    color: #1104360;  /* bleu foncé institutionnel */
    margin-top: 0;
    font-weight: bold;
}

/* === TEXTE STANDARD === */
p, li, span, div {
    color: #2e40103;
}

/* === BOUTONS === */
.stButton > button {
    background-color: #21618c;
    color: white;
    border-radius: 6px;
    border: none;
    font-weight: bold;
}
.stButton > button:hover {
    background-color: #1b4f72;
    color: white;
}

/* === SELECTBOX, SLIDER, TEXT INPUT === */
.stSelectbox, .stSlider, .stTextInput, .stTextArea {
    background-color: #ffffff;
    border: 1px solid #aab7b8;
    border-radius: 6px;
    color: #1c2833;
}

/* === ENCADRÉS D’INDICATEURS (KPIs) === */
.indicator-container {
    background-color: #2874a6;
    color: white;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    margin-bottom: 16px;
}
.indicator-title {
    font-size: 18px;
    font-weight: bold;
}
.indicator-value {
    font-size: 36px;
    font-weight: bold;
    margin-top: 10px;
}
.indicator-unit {
    font-size: 14px;
    margin-top: 4px;
}

/* === PLOTS / GRAPHIQUES === */
.stPlotlyChart {
    background-color: #ffffff;
    border: 2px solid #d10d8dc;
    border-radius: 10px;
    padding: 10px;
    box-shadow: 2px 2px 8px rgba(44, 62, 80, 0.1);
}

/* === FOCUS SELECTBOX SANS TITRE === */
.stSelectbox label {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    /* Réduction de la largeur de la sidebar */
    [data-testid="stSidebar"] {
        width: 180px !important;
    }

    /* Réduction de la marge intérieure */
    [data-testid="stSidebarContent"] {
        padding: 0.10rem 0.10rem;
    }

    /* Réduction de l'espacement entre les éléments */
    .css-1lcbmhc, .css-1e10imcs, .stRadio, .stSelectbox {
        margin-bottom: 0.4rem !important;
    }

    /* Réduction de l'espacement des titres dans la sidebar */
    .css-qrbaxs h1, .css-qrbaxs h2, .css-qrbaxs h3 {
        margin-top: 0.3rem !important;
        margin-bottom: 0.3rem !important;
    }

    /* Ajuster le contenu principal */
    .main {
        margin-left: 190px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Etats des lieux de la disponibilité des GAB ")
## Fonction pour detecter etat du GAB
def detecter_etat_gab(message):
    message = message.upper()
    if any(kw in message for kw in ["COMMUNICATION OFFLINE", "GO OUT OF SERVICE", 
                                    "COMMUNICATION ERROR", "APPLICATION STARTED",
                                    "OPERATOR DOOR OPENED","EMPTY", "REMOVED","INSERTED"]):
        return "INDISPONIBLE"
    elif any(kw in message for kw in ["COMMUNICATION ONLINE", "JOURNALING STARTED", "GO IN SERVICE", "OPERATOR DOOR CLOSED", "SAFE DOOR CLOSED", "SERVICEMODE LEFT"]):
        return "RETOUR_NORMAL"
    elif any(kw in message for kw in ["CARD RETAINED",  "IDCU ERROR","ERROR DURING CASH RETRACT",  "EDM ERROR","RECEIPT PAPER LOW","DEVICE ERROR","CASSETTE", "LOW", "REC ERROR", "JRN/REC ERROR", "*SUPPLIES STATUS*", "CASH RETRACTED", "SERVICEMODE ENTERED"]):
        return "FONCTIONNEMENT_DEGRADE"
    else:
        return "INCONNU"
## Fonction pour detecter la composante concernée

def detecter_composante(message):
    message = message.upper()
    if "CARD RETAINED" in message or "CARD" in message or "RETAINED" in message:
        return "LECTEUR_CARTE"
    elif "COMMUNICATION" in message:
        return "RESEAU_COMMUNICATION"
    elif "DOOR" in message:
        return "PORTE_COFFRE"
    elif "RECEIPT" in message or "PRINTER" in message:
        return "IMPRIMANTE"
    elif "DISPENSER" in message or "CASH" in message or "CASSETTE" in message:
        return "MODULE_DISTRIBUTION_BILLETS"
    elif "JOURNAL" in message or "REC ERROR" in message or "JRN/REC" in message:
        return "SYSTEME_JOURNALISATION"
    elif "APPLICATION" in message:
        return "APPLICATION_LOGICIELLE"
    elif "IDCU" in message:
        return "UNITE_CONTROLE_INTELLIGENTE"
    elif "CDM" in message:
        return "MODULE_DISTRIBUTION"
    elif "EDM" in message:
        return "MODULE_DEPOT"
    elif "DEVICE" in message:
        return "COMPOSANT_MATERIEL"
    else:
        return "AUTRE"
## Fonction pour  le nettoyage du message brut
def nettoyer_message(ligne):
    if "JOURNALING STARTED" in ligne:
        return "JOURNALING STARTED"
    if "APPLICATION STARTED" in ligne:
        return "APPLICATION STARTED"
    if ligne.startswith("*") and ligne.count("*") == 2:
        match = re.match(r"\*\d+\*(\d{2}:\d{2}:\d{2})\s+(.*)", ligne)
        if match:
            return match.group(2).strip()
    match = re.match(r"(\d{2}:\d{2}:\d{2})\s+(.*)", ligne)
    if match:
        return match.group(2).strip()
    return ligne.strip()
## Fonction pour extraire les incidents à partir des fichiers.jrn
def extraire_incidents(dossier_base):
    incidents = []
    for racine, _, fichiers in os.walk(dossier_base):
        ville = os.path.basename(racine)
        id_gab = None
        for fichier in fichiers:
            if not fichier.lower().endswith(".jrn"):
                continue
            chemin_fichier = os.path.join(racine, fichier)
            date_fichier = fichier.replace(".jrn", "")
            date_formatee = f"{date_fichier[6:8]}/{date_fichier[4:6]}/{date_fichier[0:4]}"
            try:
                with open(chemin_fichier, 'r', encoding='latin-1', errors='ignore') as f:
                    lignes = [l.strip() for l in f if l.strip()]
            except:
                lignes = []
            for i, ligne in enumerate(lignes):
                if "ATM:" in ligne:
                    m = re.search(r"ATM:\s*(\d+)", ligne)
                    if m:
                        id_gab = m.group(1)
                        break
                elif "GAB" in ligne and i + 1 < len(lignes):
                    m = re.search(r"(\d{6,})", lignes[i + 1])
                    if m:
                        id_gab = m.group(1)
                        break
                else:
                    m = re.search(r"(ID GAB:?)[^\d]*(\d{6,})", ligne)
                    if m:
                        id_gab = m.group(2)
                        break
            if not lignes:
                incidents.append({
                    "ID_GAB": id_gab,
                    "DATE": date_formatee,
                    "HEURE": None,
                    "MESSAGE_BRUT": "Le GAB n’a pas fonctionné",
                    "COMPOSANTE_CONCERNEE": "INCONNUE",
                    "ETAT_GAB": "INDISPONIBLE"
                })
                continue
            for ligne in lignes:
                ligne = ligne.strip()
                if ("JOURNALING STARTED" in ligne or "APPLICATION STARTED" in ligne) or \
                   (ligne.startswith("*") and ligne.count("*") == 2):
                    heure = None
                    if ligne.startswith("*"):
                        match = re.search(r"\*\d+\*(\d{2}:\d{2}:\d{2})", ligne)
                        if match:
                            heure = match.group(1)
                    else:
                        match = re.match(r"(\d{2}:\d{2}:\d{2})", ligne)
                        if match:
                            heure = match.group(1)
                    message_nettoye = nettoyer_message(ligne)
                    incidents.append({
                        "ID_GAB": id_gab,
                        "DATE": date_formatee,
                        "HEURE": heure,
                        "MESSAGE_BRUT": message_nettoye,
                        "COMPOSANTE_CONCERNEE": detecter_composante(message_nettoye),
                        "ETAT_GAB": detecter_etat_gab(message_nettoye)
                    })
    return incidents


# === Lancer l'extraction
#dossier_logs = "c://Users//TIAO ELIASSE//Desktop//ISE320210//PREPARATION_GT//Document_Afriland//Données//Logs"
#data_incidents = extraire_incidents(dossier_logs)
#df_incidents = pd.DataFrame(data_incidents)

#@st.cache_data
#def charger_donnees(path):
   # return pd.read_parquet(path)
#path=r'c:\Users\TIAO ELIASSE\Desktop\ISE32025\PREPARATION_GT\Document_Afriland\Données_travail\Base_incident\base_incidents.parquet'

# Étape 1 : Charger la base
#uploaded_file = st.file_uploader("📁 Veuillez sélectionner votre base de données (CSV ou Excel)", type=["csv", "xlsx"])

uploaded_zip = st.file_uploader("Veuillez importer un fichier .zip contenant un fichier .csv", type=["zip"])

if uploaded_zip is not None:
    try:
        with zipfile.ZipFile(uploaded_zip, "r") as z:
            # Lister les fichiers dans l'archive
            fichier_csv = [f for f in z.namelist() if f.endswith(".csv")]

            if not fichier_csv:
                st.error("❌ Aucun fichier CSV trouvé dans le ZIP.")
            else:
                # Si plusieurs fichiers CSV, permettre la sélection
                if len(fichier_csv) > 1:
                    nom_csv = st.selectbox("Plusieurs fichiers trouvés, choisissez-en un :", fichier_csv)
                else:
                    nom_csv = fichier_csv[0]

                # Lecture du CSV dans un DataFrame
                with z.open(nom_csv) as f:
                    df_incidents = pd.read_csv(f, encoding="utf-8", engine="python")  # adapter encodage si besoin
                    df_incidents["ID_GAB"] = df_incidents["ID_GAB"].astype(str)
                    st.success(f"✅ Fichier '{nom_csv}' chargé avec succès !")
               


#df_incidents=pd.read_csv("c://Users//TIAO ELIASSE//Desktop//ISE32025//PREPARATION_GT//Document_Afriland//Données_travail//Base_incident//base_incidents2.csv")
#df_incidents=charger_donnees(path)
#Remplacons des modalités

# === Export vers Excel
#chemin_sortie = "c://Users//TIAO ELIASSE//Desktop//ISE320210//PREPARATION_GT//Document_Afriland//Données//Bse de données _construits//base_incidents_GAB_nettoyee_etat_corres_final.xlsx"
#df_incidents.to_excel(chemin_sortie, index=False)

#print("✅ Export terminé avec succès :", chemin_sortie)


    ### Indisponibilité par message et retour à normal
    # cette fonction calcule la durée d'indisponibilité journalier causé par un évenement donnée

        def calcul_duree_indisponibilite_par_message_et_retour(df_incidents):
            # Conversion de la date et de l'heure en datetime
            df = df_incidents.copy()
            df["DATE"] = pd.to_datetime(df["DATE"], format="%d/%m/%Y", errors="coerce")
            df["DATETIME"] = pd.to_datetime(df["DATE"].dt.strftime("%d/%m/%Y") + " " + df["HEURE"],
                                            format="%d/%m/%Y %H:%M:%S", errors="coerce")
            df = df[df["DATETIME"].notnull()].sort_values([ "ID_GAB", "DATE", "DATETIME"])
    
            resultats = []
    
            # Parcours des groupes par jour et GAB
            for ( id_gab, date), groupe in df.groupby([ "ID_GAB", "DATE"]):
                indispo_debut = None
                message_debut = None
    
                for _, ligne in groupe.iterrows():
                    etat = ligne["ETAT_GAB"]
                    dt = ligne["DATETIME"]
                    msg = ligne["MESSAGE_BRUT"]
    
                    if etat == "INDISPONIBLE" and indispo_debut is None:
                        indispo_debut = dt
                        message_debut = msg
    
                    elif etat == "RETOUR_NORMAL" and indispo_debut is not None:
                        duree = (dt - indispo_debut).total_seconds() / 60  # en minutes
                        resultats.append({
                            "ID_GAB": id_gab,
                            "DATE": date,
                            "ETAT_GAB": "INDISPONIBLE",
                            "MESSAGE_BRUT": message_debut,
                            "NB_OCCURRENCES": 1,
                            "DUREE (en minutes)": round(duree, 2)
                        })
                        resultats.append({
                            "ID_GAB": id_gab,
                            "DATE": date,
                            "ETAT_GAB": "RETOUR_NORMAL",
                            "MESSAGE_BRUT": msg,
                            "NB_OCCURRENCES": 1,
                            "DUREE (en minutes)": 0
                        })
                        indispo_debut = None
                        message_debut = None
    
                # Cas où la journée se termine en état INDISPONIBLE
                if indispo_debut is not None:
                    fin_journee = datetime.strptime(f"{date.strftime('%d/%m/%Y')} 23:59:59", "%d/%m/%Y %H:%M:%S")
    
                    duree = (fin_journee - indispo_debut).total_seconds() / 60
                    resultats.append({
                        "ID_GAB": id_gab,
                        "DATE": date,
                        "ETAT_GAB": "INDISPONIBLE",
                        "MESSAGE_BRUT": message_debut,
                        "NB_OCCURRENCES": 1,
                        "DUREE (en minutes)": round(duree, 2)
                    })
    
            # Création du DataFrame final
            df_resultat = pd.DataFrame(resultats)
    
            # Ordonner le résultat
            df_resultat = df_resultat.sort_values(["ID_GAB", "DATE", "ETAT_GAB", "MESSAGE_BRUT"])
    
            return df_resultat
    
    
        # --- Graphique 1 : Pannes par message ---
        import plotly.express as px
        import streamlit as st
    
        import streamlit as st
        import plotly.express as px
    
        def afficher_duree_indisponibilite(df_panne, group_col, value_col,Mode_affichage="Valeurs absolues"):
            """
            Affiche un graphique en barres horizontales de la durée totale d'indisponibilité,
            soit en valeurs absolues, soit en proportions (%).
    
            Paramètres :
            - df : DataFrame filtré contenant les pannes
            - group_col : colonne pour regrouper (ex : 'MESSAGE_BRUT')
            - value_col : colonne de durée à sommer (ex : 'DUREE (en minutes)')
            """
            
            # Filtrer les pannes
            #df_panne = df[df["ETAT_GAB"] == "INDISPONIBLE"].copy()
    
            # Groupement
            df_grouped = (
                df_panne.groupby(group_col)[value_col]
                .sum()
                .reset_index()
                .sort_values(by=value_col, ascending=False)
            )
    
            # Calcul du pourcentage si demandé
            if mode_affichage == "Proportions (%)":
                total = df_grouped[value_col].sum()
                df_grouped["POURCENTAGE"] = (df_grouped[value_col] / total * 100).round(2)
                x_col = "POURCENTAGE"
                #title = f"Durée d’indisponibilité par {group_col.lower()} (en %)"
            else:
                x_col = value_col
                #title = f"Durée totale d’indisponibilité par {group_col.lower()}"
    
            # Affichage du graphique
            fig = px.bar(
                df_grouped,
                x=x_col,
                y=group_col,
                orientation="h",
                #title=title,
                text=x_col
            )
    
            st.plotly_chart(fig, use_container_width=True)
    
        #import plotly.express as px
        #import streamlit as st
    
        def afficher_duree_indisponibilite_top(df_panne, group_col, value_col, 
                                            mode_affichage="Valeurs absolues", 
                                            top_ou_flop="TOP"):
            """
            Affiche un graphique en barres horizontales de la durée d’indisponibilité ou sa proportion.
            
            Paramètres :
            - df_panne : DataFrame filtré contenant les pannes
            - group_col : colonne de regroupement (ex : 'MESSAGE_BRUT')
            - value_col : colonne contenant la durée à sommer (ex : 'DUREE (en minutes)')
            - mode_affichage : "Valeurs absolues" ou "Proportions (%)"
            - top_ou_flop : "TOP" pour les plus élevés, "FLOP" pour les plus faibles
            """
    
            # Agréger les données
            df_grouped = (
                df_panne.groupby(group_col)[value_col]
                .sum()
                .reset_index()
            )
            
            df_grouped1= df_grouped.sort_values(by=value_col).copy()
            
            # Trier selon le choix TOP/FLOP
    
            asc = True if top_ou_flop == "FLOP" else False
            
            df_grouped = df_grouped.sort_values(by=value_col, ascending=asc).head(10)
    
            # Affichage en pourcentage ?
            if mode_affichage == "Proportions (%)":
                total = df_grouped1[value_col].sum()
                df_grouped["POURCENTAGE"] = (df_grouped[value_col] / total * 100).round(4)
                x_col = "POURCENTAGE"
                titre = f"{top_ou_flop} 10 par {group_col.lower()} (en %)"
            else:
                x_col = value_col
                titre = f"{top_ou_flop} 10 par message d'alerte"
            
                #titre = f"{top_ou_flop} 10 par {group_col.lower()} (durée en minutes)"
    
            # Graphique
            fig = px.bar(
                df_grouped,
                x=x_col,
                y=group_col,
                orientation="h",
                text=x_col,
                title=titre
            )
    
            fig.update_traces(texttemplate='%{text}', textposition='outside')
            fig.update_layout(yaxis_title=group_col, xaxis_title=x_col)
    
            st.plotly_chart(fig, use_container_width=True)
    
        ## Interessons nous uniquement aux incidents donnnant lieu à des indisponibilité totales
        df_pannes = df_incidents[df_incidents["ETAT_GAB"].isin(["INDISPONIBLE","RETOUR_NORMAL"])]
        df_pannes_jour_durée=calcul_duree_indisponibilite_par_message_et_retour(df_pannes)
    
    
    
        df_pannes_jour_durée_sans_normal=df_pannes_jour_durée[df_pannes_jour_durée['ETAT_GAB']=="INDISPONIBLE"]
    
        def regrouper_par_mois(df_dispo):
            # Assurer que la colonne DATE est au bon format datetime
            df = df_dispo.copy()
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    
            # Créer une colonne ANNEE_MOIS pour le regroupement
            df["DATE"] = df["DATE"].dt.to_period("M").astype(str)
    
            # Agréger les valeurs
            df_mensuel = df.groupby(["ID_GAB", "DATE", "ETAT_GAB", "MESSAGE_BRUT"]).agg({
                "NB_OCCURRENCES": "sum",
                "DUREE (en minutes)": "sum"
            }).reset_index()
    
            return df_mensuel
    
    
        ### Fonctions pour la construction de la base pour le calcul dedisponibilité
    
        import pandas as pd
        from datetime import datetime, timedelta
    
        from datetime import datetime, timedelta
        import pandas as pd
    
        def construire_base_disponibilite_avec_taux(df_incidents):
            # Étape 1 : Ajouter la colonne ETAT_GAB
            df = df_incidents.copy()
            df["ETAT_GAB"] = df["MESSAGE_BRUT"].apply(detecter_etat_gab)
    
            # Nettoyage des lignes sans heure
            df = df[df["HEURE"].notnull()].copy()
    
            # Conversion en datetime
            df["DATE"] = pd.to_datetime(df["DATE"], format="%d/%m/%Y", errors="coerce")
            df["DATETIME"] = pd.to_datetime(
                df["DATE"].dt.strftime("%d/%m/%Y") + " " + df["HEURE"],
                format="%d/%m/%Y %H:%M:%S",
                errors="coerce"
            )
    
            # Nettoyage des valeurs nulles
            df = df[df["DATETIME"].notnull()].sort_values(["ID_GAB", "DATE", "DATETIME"])
    
            resultats = []
    
            # Parcours des événements par GAB et par jour
            for (id_gab, date), groupe in df.groupby(["ID_GAB", "DATE"]):
                indispo_total = timedelta(0)
                indispo_debut = None
    
                for _, ligne in groupe.iterrows():
                    etat = ligne["ETAT_GAB"]
                    heure = ligne["DATETIME"]
    
                    if etat == "INDISPONIBLE" and indispo_debut is None:
                        indispo_debut = heure
    
                    elif etat == "RETOUR_NORMAL" and indispo_debut is not None:
                        indispo_total += (heure - indispo_debut)
                        indispo_debut = None
    
                # Si l'indisponibilité n’a pas été clôturée avant la fin de journée
                if indispo_debut is not None:
                    fin_journee = datetime.combine(date, datetime.max.time()).replace(hour=23, minute=59, second=59)
                    indispo_total += (fin_journee - indispo_debut)
    
                # Calculs de durées et taux
                total_journee_minutes = 24 * 60
                indispo_minutes = indispo_total.total_seconds() / 60
                dispo_minutes = max(0, total_journee_minutes - indispo_minutes)
    
                taux_dispo = dispo_minutes / total_journee_minutes
                taux_indispo = indispo_minutes / total_journee_minutes
    
                resultats.append({
                    "ID_GAB": id_gab,
                    "DATE": date.strftime("%d/%m/%Y"),
                    "Temps_d_indisponibilite (min)": round(indispo_minutes, 2),
                    "Temps_de_disponibilite (min)": round(dispo_minutes, 2),
                    "Taux de disponibilité (%)": round(taux_dispo * 100, 2),
                    "Taux d'indisponibilité (%)": round(taux_indispo * 100, 2)
                })
    
            return pd.DataFrame(resultats)
    
    
    
        def visualiser_taux_disponibilite(df, granularite="Jour", cible="Taux de disponibilité (%)"):
            """
            Affiche un graphique interactif du taux de disponibilité ou d’indisponibilité,
            regroupé par jour, mois ou année.
            
            Paramètres :
            - df : DataFrame contenant les colonnes 'DATE' et le taux cible
            - granularite : "Jour", "Mois", "Année"
            - cible : "Taux de disponibilité (%)" ou "Taux d'indisponibilité (%)"
            """
    
            # Convertir la colonne DATE si ce n’est pas déjà fait
            df = df.copy()
            df["DATE"] = pd.to_datetime(df["DATE"], format="%d/%m/%Y", errors="coerce")
    
            # Regrouper selon la granularité
            if granularite == "Jour":
                df["PERIODE"] = df["DATE"]
            elif granularite == "Mois":
                df["PERIODE"] = df["DATE"].dt.to_period("M").apply(lambda r: r.start_time)
            elif granularite == "Année":
                df["PERIODE"] = df["DATE"].dt.to_period("Y").apply(lambda r: r.start_time)
            else:
                st.error("Granularité invalide. Choisissez : Jour, Mois ou Année.")
                return
    
            # Moyenne par période
            df_agg = df.groupby("PERIODE")[cible].mean().reset_index()
    
            # Affichage du graphique
            titre = f"📊 {cible} par {granularite.lower()}"
            fig = px.line(
                df_agg,
                x="PERIODE",
                y=cible,
                markers=True,
                title=titre,
                labels={"PERIODE": granularite, cible: cible}
            )
            st.plotly_chart(fig, use_container_width=True)
    
    
        ## Fonction pour visualiser les taux de disponibilité par GAB
        def visualiser_taux_disponibilite_par_gab(df, var="ID_GAB", top_ou_flop="TOP"):
                """
                Affiche un histogramme du taux de disponibilité global par GAB (ou autre variable),
                selon le choix : 'TOP' (disponibilités élevées) ou 'FLOP' (disponibilités faibles).
    
                Paramètres :
                - df : DataFrame avec les durées de dispo/indispo
                - var : variable de regroupement (ex: "ID_GAB", "VILLE")
                - top_ou_flop : 'TOP' pour les meilleurs taux, 'FLOP' pour les plus faibles
                """
    
                # Agréger les durées par GAB ou variable choisie
                df_gab = df.groupby(var).agg({
                    "Temps_de_disponibilite (min)": "sum",
                    "Temps_d_indisponibilite (min)": "sum"
                }).reset_index()
    
                # Calcul du taux
                df_gab["Taux de disponibilité (%)"] = (
                    df_gab["Temps_de_disponibilite (min)"] /
                    (df_gab["Temps_de_disponibilite (min)"] + df_gab["Temps_d_indisponibilite (min)"])
                ) * 100
    
                # Sélection du top 10
                if top_ou_flop == "TOP":
                    df_top = df_gab.sort_values(by="Taux de disponibilité (%)", ascending=False).head(10)
                    titre = f"🔝 TOP 10 {var} ayant des taux de disponibilités élevés "
                else:
                    df_top = df_gab.sort_values(by="Taux de disponibilité (%)", ascending=True).head(10)
                    titre = f"🔻 TOP 10 {var} ayant des taux de disponibilités faibles "
    
                # Affichage du graphique
                fig = px.bar(
                    df_top,
                    x=var,
                    y="Taux de disponibilité (%)",
                    text="Taux de disponibilité (%)",
                    title=titre,
                    labels={var: var, "Taux de disponibilité (%)": "Taux (%)"},
                    height=1000
                )
    
                fig.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
                fig.update_layout(xaxis_tickangle=-410)
    
                st.plotly_chart(fig, use_container_width=True)
    
            
        def compter_messages_incidents_moins_grave_par_jour(df_incidents):
            # Assurer que les colonnes sont bien typées
            df = df_incidents.copy()
            df["DATE"] = pd.to_datetime(df["DATE"], format="%d/%m/%Y", errors="coerce")
    
            # Groupement par VILLE, ID_GAB, DATE, MESSAGE_BRUT puis comptage
            comptage = (
                df.groupby(["ID_GAB", "DATE", "MESSAGE_BRUT","ETAT_GAB"])
                .size()
                .reset_index(name="NB_OCCURRENCES")
    
            )
            return comptage
        df_pannes_jour_durée_sans_normal=df_pannes_jour_durée[df_pannes_jour_durée["ETAT_GAB"]=="INDISPONIBLE"]
    
        df_dispo_mois=regrouper_par_mois(df_pannes_jour_durée_sans_normal)
    
        # --- Chargement des données ---
        # df_resultat = calcul_duree_indisponibilite_par_message_et_retour(df_incidents)
        df =df_pannes_jour_durée_sans_normal.copy()# Exemple de 
    
        #st.set_page_config(page_title="Tableau de bord GAB", layout="wide")
    
        st.sidebar.markdown("### 🎯 Forme d'analyse")
    
        forme_analyse = st.sidebar.radio(
                "Sélectionnez la forme d'analyse",
                options=['Ensemble', "Analyse par GAB"]
            )
        base_taux_disponibilite=construire_base_disponibilite_avec_taux(df_incidents)
        if forme_analyse=="Ensemble":
        # --- KPIs ---
    
            
    
            # --- Filtres interactifs ---
            #st.sidebar.header("🔍 Filtres")
            #villes = st.multiselect("Sélectionnez la ou les villes", options=sorted(df["VILLE"].unique()), default=df["VILLE"].unique())
            #df_ville=df[df["VILLE"].isin(villes)]
    
            #gabs = st.multiselect("Sélectionnez un ou plusieurs GAB", options=sorted(df_ville["ID_GAB"].unique()), default=df_ville["ID_GAB"].unique())
            
    
            #df_gab=df_ville[df_ville["ID_GAB"].isin(gabs)]
            df_gab=df.copy()
            dates = st.date_input("Période", [df_gab["DATE"].min(), df_gab["DATE"].max()])
    
            df_date=df[(df_gab["DATE"] >= pd.to_datetime(dates[0])) & (df_gab["DATE"] <= pd.to_datetime(dates[1]))]
            total_pannes = df_date[df_date["ETAT_GAB"] == "INDISPONIBLE"]["NB_OCCURRENCES"].sum()
            duree_totale = df_date[df_date["ETAT_GAB"] == "INDISPONIBLE"]["DUREE (en minutes)"].sum()
            nb_gabs = df_date["ID_GAB"].nunique()
            # Somme des temps
            base_taux_disponibilite["DATE"] = pd.to_datetime(base_taux_disponibilite["DATE"], dayfirst=True, errors="coerce")
    
            df_date_taux=base_taux_disponibilite[(base_taux_disponibilite["DATE"] >= pd.to_datetime(dates[0])) & (base_taux_disponibilite["DATE"] <= pd.to_datetime(dates[1]))]
            total_dispo = df_date_taux["Temps_de_disponibilite (min)"].sum()
            total_indispo = df_date_taux["Temps_d_indisponibilite (min)"].sum()
            temps_total = total_dispo + total_indispo
    
            # Calcul du taux
            taux_dispo = (total_dispo / temps_total) * 100 if temps_total > 0 else 0
    
    
            st.markdown("### 📊 Statistiques globales sur la disponibilité des GAB")
    
    
            # Première ligne : Incidents + Durée totale
            ligne1_col1, ligne1_col2 = st.columns(2)
    
            with ligne1_col1:
                st.markdown(f"""
                <div style="background-color:#fceae8; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#b00020; margin-bottom:10px;">🚧 Incidents d'indisponibilité</h4>
                    <h1 style="color:#900c3f; font-size:36px;">{total_pannes}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            with ligne1_col2:
                st.markdown(f"""
                <div style="background-color:#e8f10e9; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#2e7d32; margin-bottom:10px;">⏱ Durée totale d’indisponibilité (min)</h4>
                    <h1 style="color:#1b10e20; font-size:36px;">{duree_totale:.0f}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            # Deuxième ligne : GAB + Taux de disponibilité
            ligne2_col1, ligne2_col2 = st.columns(2)
    
            with ligne2_col1:
                st.markdown(f"""
                <div style="background-color:#e3f2fd; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#110610c0; margin-bottom:10px;">🏦 GAB impliqués</h4>
                    <h1 style="color:#0d47a1; font-size:36px;">{nb_gabs}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            with ligne2_col2:
                st.markdown(f"""
                <div style="background-color:#f1f8e9; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#10108b2f; margin-bottom:10px;">📈 Taux de disponibilité global</h4>
                    <h1 style="color:#33691e; font-size:36px;">{taux_dispo:.2f} %</h1>
                </div>
                """, unsafe_allow_html=True)
    
        # col2.metric("Taux de disponibilité global", f"{taux_dispo:.2f} %")
            #df=df_date.copy()
            # --- Filtrage des données ---
            #df["DATE"] = pd.to_datetime(df["DATE"])
            #df_filtre = df[
            #"" (df["VILLE"].isin(villes)) &
                #(df["ID_GAB"].isin(gabs)) &
                #(df["DATE"] >= pd.to_datetime(dates[0])) &
                #(df["DATE"] <= pd.to_datetime(dates[1]))
            #]
    
    
            
            # Choix en dehors de la fonction
            choix = st.radio(
            "Afficher le classement suivant :",
            ["TOP", "FLOP"],
            format_func=lambda x: "🔝 Meilleurs taux" if x == "TOP" else "🔻 Pires taux"
        )
    
        # Appel avec le choix
            base_taux_disponibilite["ID_GAB"] = base_taux_disponibilite["ID_GAB"].astype("category")
    
            visualiser_taux_disponibilite_par_gab(base_taux_disponibilite, var="ID_GAB", top_ou_flop=choix)
    
    
            #visualiser_taux_disponibilite_par_gab(base_taux_disponibilite,"VILLE")
    
            # Choix de mode d'affichage
            import streamlit as st
    
            # Section titre claire
            st.markdown("### 🎯 Sélection du mode d'affichage des résultats")
    
            # Espacement
            #st.markdown("---")
    
            # Mise en page centrée avec 3 colonnes
            col1, col2, col3 = st.columns([1, 2, 1])  # colonne centrale plus large
    
            with col2:
                mode_affichage = st.selectbox(
                    label="",
                    options=["📊 Valeurs totales", "📈 Proportions (%)"],
                    index=0
                )
    
    
    
            col=st.columns(2)
            with col[0]:
                if mode_affichage == "Valeurs totales":
                    st.write("📊 Durée d'indisponibilité par évenement")
                else:
                    st.write("📊 poids selon la durée d'indisponibilité par évenement")
                #st.write("📊 Durée d'indisponibilité par évenement")
                afficher_duree_indisponibilite(df, "MESSAGE_BRUT", "DUREE (en minutes)",mode_affichage)
            with col[1]:
                if mode_affichage == "Valeurs totales":
                    st.write("📊 Nombre d'indisponibilité par évenement")
                else:
                    st.write("📊 poids selon le nombre d'indisponibilité par évenement")
                #st.write("📊 Nombre d'indisponibilité par évenement")
                afficher_duree_indisponibilite(df, "MESSAGE_BRUT", "NB_OCCURRENCES",mode_affichage)
    
            # --- Graphique 2 : évolution dans le temps ---
            # --- Graphique 2 : évolution dans le temps ---
            st.subheader("⏰ Évolution de l'indisponibilité")
            
            # Choix de la granularité temporelle
            granularite = st.selectbox(
                "Choisissez la granularité temporelle :", 
                options=["Jour", "Semaine", "Mois", "Année"]
            )
            visualiser_taux_disponibilite(base_taux_disponibilite, granularite, cible="Taux de disponibilité (%)")
            
            # --- Détail des pannes ---
            #st.subheader("🔢 Données détaillées")
            #st.dataframe(df_filtre.sort_values("DATE", ascending=False))
            st.subheader("📊 Etats des lieux des messages d'alertes")
            df_defaut_mais_fonction=df_incidents[df_incidents["ETAT_GAB"]=="FONCTIONNEMENT_DEGRADE"]
            #st.write("df :",df_defaut_mais_fonction)
            df=compter_messages_incidents_moins_grave_par_jour(df_defaut_mais_fonction)
            col1, col2, col3 = st.columns([1, 2, 1])  # colonne centrale plus large
    
            with col2:
                mode_affichage = st.selectbox("Mode d'affichage", ["Valeurs absolues", "Proportions (%)"], key="mode_affichage_indispo")
                top_flop = st.radio("Afficher :", ["TOP", "FLOP"], format_func=lambda x: "🟢 TOP 10 " if x == "TOP" else "🔴 Flop 10", key="choix_top_flop")
    
    
        # col=st.columns(2)
        # with col[0]:
            if mode_affichage == "Valeurs totales":
                    st.write("📊 Nombre   d'arlertes")
            else:
                st.write("📊 poids par message d'alerte")
                #st.write("📊 Durée d'indisponibilité par évenement")
            afficher_duree_indisponibilite_top(df, group_col="MESSAGE_BRUT",value_col="NB_OCCURRENCES", 
                                    mode_affichage=mode_affichage, top_ou_flop=top_flop)
    
            #afficher_duree_indisponibilite(df, "MESSAGE_BRUT", "NB_OCCURRENCES")
            
        else:
            base_taux_disponibilite["DATE"] = pd.to_datetime(base_taux_disponibilite["DATE"], dayfirst=True, errors="coerce")
            #Ville=df['VILLE'].unique()
            #Ville=st.sidebar.selectbox("selectionnez le GAB",Ville )
            #df=df[df["VILLE"]==Ville].copy()
            df_disponibilité=base_taux_disponibilite.copy()
            
            df_incidents=df_incidents.copy()
    
            # --- Filtres interactifs ---
            #st.sidebar.header("🔍 Filtres")
            #villes = st.multiselect("Sélectionnez la ou les villes", options=sorted(df["VILLE"].unique()), default=df["VILLE"].unique())
            #df_ville=df[df["VILLE"].isin(villes)]
    
            gabs = st.sidebar.selectbox("Sélectionnez un ou plusieurs GAB", df["ID_GAB"].unique())
    
            df_gab=df[df["ID_GAB"]==gabs].copy()
            #df_gab=df.copy()
            dates = st.date_input("Période", [df_gab["DATE"].min(), df_gab["DATE"].max()])
    
    
            df_date=df_gab[(df_gab["DATE"] >= pd.to_datetime(dates[0])) & (df_gab["DATE"] <= pd.to_datetime(dates[1]))]
            total_pannes = df_date[df_date["ETAT_GAB"] == "INDISPONIBLE"]["NB_OCCURRENCES"].sum()
            duree_totale = df_date[df_date["ETAT_GAB"] == "INDISPONIBLE"]["DUREE (en minutes)"].sum()
            nb_gabs = df_date["ID_GAB"].nunique()
            # Somme des temps
            
            df_disponibilité= df_disponibilité[df_disponibilité['ID_GAB']== gabs].copy()
            df_date_taux=df_disponibilité[(df_disponibilité["DATE"] >= pd.to_datetime(dates[0])) & (df_disponibilité["DATE"] <= pd.to_datetime(dates[1]))]
            
            total_dispo = df_date_taux["Temps_de_disponibilite (min)"].sum()
            total_indispo = df_date_taux["Temps_d_indisponibilite (min)"].sum()
            temps_total = total_dispo + total_indispo
    
            # Calcul du taux
            taux_dispo = (total_dispo / temps_total) * 100 if temps_total > 0 else 0
    
    
            st.markdown("### 📊 Statistiques globales sur la disponibilité des GAB")
    
    
            # Première ligne : Incidents + Durée totale
            ligne1_col1, ligne1_col2 = st.columns(2)
    
            with ligne1_col1:
                st.markdown(f"""
                <div style="background-color:#fceae8; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#b00020; margin-bottom:10px;">🚧 Incidents d'indisponibilité</h4>
                    <h1 style="color:#900c3f; font-size:36px;">{total_pannes}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            with ligne1_col2:
                st.markdown(f"""
                <div style="background-color:#e8f10e9; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#2e7d32; margin-bottom:10px;">⏱ Durée totale d’indisponibilité (min)</h4>
                    <h1 style="color:#1b10e20; font-size:36px;">{duree_totale:.0f}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            # Deuxième ligne : GAB + Taux de disponibilité
            ligne2_col1, ligne2_col2 = st.columns(2)
    
            with ligne2_col1:
                st.markdown(f"""
                <div style="background-color:#e3f2fd; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#110610c0; margin-bottom:10px;">🏦 GAB impliqués</h4>
                    <h1 style="color:#0d47a1; font-size:36px;">{nb_gabs}</h1>
                </div>
                """, unsafe_allow_html=True)
    
            with ligne2_col2:
                st.markdown(f"""
                <div style="background-color:#f1f8e9; padding:24px; border-radius:12px; text-align:center;
                            box-shadow:0 4px 12px rgba(0,0,0,0.1); margin-bottom:20px;">
                    <h4 style="color:#10108b2f; margin-bottom:10px;">📈 Taux de disponibilité global</h4>
                    <h1 style="color:#33691e; font-size:36px;">{taux_dispo:.2f} %</h1>
                </div>
                """, unsafe_allow_html=True)
    
            #df=df_date.copy()
            # --- Filtrage des données ---
            #df["DATE"] = pd.to_datetime(df["DATE"])
            #df_filtre = df[
            #"" (df["VILLE"].isin(villes)) &
                #(df["ID_GAB"].isin(gabs)) &
                #(df["DATE"] >= pd.to_datetime(dates[0])) &
                #(df["DATE"] <= pd.to_datetime(dates[1]))
            #]
    
    
    
            # Choix de mode d'affichage
            import streamlit as st
    
            # Section titre claire
            st.markdown("### 🎯 Sélection du mode d'affichage des résultats")
    
            # Espacement
            #st.markdown("---")
    
            # Mise en page centrée avec 3 colonnes
            col1, col2, col3 = st.columns([1, 2, 1])  # colonne centrale plus large
    
            with col2:
                mode_affichage = st.selectbox(
                    label="",
                    options=["📊 Valeurs totales", "📈 Proportions (%)"],
                    index=0
                )
    
    
    
            col=st.columns(2)
            with col[0]:
                if mode_affichage == "Valeurs totales":
                    st.write("📊 Durée d'indisponibilité par évenement")
                else:
                    st.write("📊 poids selon la durée d'indisponibilité par évenement")
                #st.write("📊 Durée d'indisponibilité par évenement")
                afficher_duree_indisponibilite(df, "MESSAGE_BRUT", "DUREE (en minutes)",mode_affichage)
            with col[1]:
                if mode_affichage == "Valeurs totales":
                    st.write("📊 Nombre d'indisponibilité par évenement")
                else:
                    st.write("📊 poids selon le nombre d'indisponibilité par évenement")
                #st.write("📊 Nombre d'indisponibilité par évenement")
                afficher_duree_indisponibilite(df, "MESSAGE_BRUT", "NB_OCCURRENCES",mode_affichage)
    
            # --- Graphique 2 : évolution dans le temps ---
            # --- Graphique 2 : évolution dans le temps ---
            st.subheader("⏰ Évolution de l'indisponibilité")
    
            # Choix de la granularité temporelle
            granularite = st.selectbox(
                "Choisissez la granularité temporelle :", 
                options=["Jour", "Mois", "Année"]
            )
            visualiser_taux_disponibilite(df_disponibilité, granularite, cible="Taux de disponibilité (%)")
            st.subheader("📊 Etats des lieux des messages d'alertes")
    
            df_gab=df_incidents.copy()
            df_gab["DATE"] = pd.to_datetime(df_gab["DATE"], dayfirst=True, errors="coerce")
            # Sélection de la période
            st.markdown("### 🗓️ Sélection de la période d’analyse")
            #dates = st.date_input("Période", [df_gab["DATE"].min(), df_gab["DATE"].max()], key="date_input_indispo")
    
            # Validation de la sélection
            if len(dates) != 2:
                st.warning("⚠️ Veuillez sélectionner une **période complète** (deux dates).")
            else:
                date_debut, date_fin = dates
                if date_debut > date_fin:
                    st.warning("⚠️ La **date de début** ne peut pas être **postérieure** à la date de fin.")
                else:
                    dates = st.date_input("Période", [df_gab["DATE"].min(), df_gab["DATE"].max()],key="date_input_indispo")
    
                    df_date=df_gab[(df_gab["DATE"] >= pd.to_datetime(dates[0])) & (df_gab["DATE"] <= pd.to_datetime(dates[1]))]
                    df_defaut_mais_fonction=df_date[df_date["ETAT_GAB"]=="FONCTIONNEMENT_DEGRADE"]
                    #st.write("df :",df_defaut_mais_fonction)
                    df=compter_messages_incidents_moins_grave_par_jour(df_defaut_mais_fonction)
                    col1, col2, col3 = st.columns([1, 2, 1])  # colonne centrale plus large
                
                    with col2:
                        mode_affichage = st.selectbox("Mode d'affichage", ["Valeurs absolues", "Proportions (%)"], key="mode_affichage_indispo")
                        top_flop = st.radio("Afficher :", ["TOP", "FLOP"], format_func=lambda x: "🟢 TOP 10 " if x == "TOP" else "🔴 Flop 10", key="choix_top_flop")
    
    
                # col=st.columns(2)
                # with col[0]:
                    if mode_affichage == "Valeurs totales":
                            st.write("📊 Nombre   d'arlertes")
                    else:
                        st.write("📊 poids par message d'alerte")
                        #st.write("📊 Durée d'indisponibilité par évenement")
                    afficher_duree_indisponibilite_top(df, group_col="MESSAGE_BRUT",value_col="NB_OCCURRENCES", 
                                            mode_affichage=mode_affichage, top_ou_flop=top_flop)
    except zipfile.BadZipFile:
        st.error("❌ Le fichier fourni n’est pas un fichier ZIP valide.")
    except Exception as e:
        st.error(f"❌ Une erreur est survenue : {e}")
else:
    st.info("⬆️ Veuillez importer un fichier ZIP.")
