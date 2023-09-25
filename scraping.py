from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium import webdriver
import time
import json

#Extract Text from any web pages.
entry_url = input("Enter Your URL : ")
driver = webdriver.Chrome()
try:
    driver.get(entry_url)
except:
    print(f"Couldn't open {entry_url}")
time.sleep(1)
driver.maximize_window()
text = driver.find_element(By.XPATH, "/html/body").text
all_text = text.replace("\n"," ")


# For Link Extraction.
def extract_links_by_tagName(tag_name):
    links = set()
    try:
        a_elems = driver.find_elements(By.TAG_NAME, tag_name)
        for elem in a_elems:
            link = elem.get_attribute("href")
            if link == "javascript:void(0)":
                continue
            # Remove links to images and various files (if needed)
            # You can customize this part to filter links as desired
            if (
                link.endswith(".png")
                or link.endswith(".json")
                or link.endswith(".txt")
                or link.endswith(".svg")
                or link.endswith(".ipynb")
                or link.endswith(".jpg")
                or link.endswith(".pdf")
                or link.endswith(".mp4")
                or "mailto" in link
                or len(link) > 300
            ):
                continue
            # Remove anchors
            link = link.split("#")[0]
            # Remove parameters
            link = link.split("?")[0]
            # Remove trailing forward slash
            link = link.rstrip("/")
            links.add(link)
        return list(links)
    except:
        return []
    
all_links = extract_links_by_tagName("a")

# Lists of class names
top_nav_class = ["top-navigation", "header-main__slider", "navbar", "navbar-nav", "menu", "nav", "header", "top-bar"]
left_nav_class = ["left-navigation", "nav-menu", "sideBar"]
collected_links = []

# Loop through the top navigation class names
for class_name in top_nav_class:
    try:
        element = driver.find_element(By.CLASS_NAME,class_name)
        elements = element.find_elements(By.TAG_NAME,'a')
        for element in elements:
            link = element.get_attribute('href')
            if link:
                link = link.split("#")[0]
                link = link.split("?")[0]
                link = link.rstrip("/")
            if link:
                collected_links.append(link)
    except NoSuchElementException:
        # Handle the case when the class name is not found
        pass

# Loop through the left navigation class names
for class_name in left_nav_class:
    try:
        element = driver.find_element(By.CLASS_NAME,class_name)
        elements = element.find_elements(By.TAG_NAME,'a')
        for element in elements:
            link = element.get_attribute('href')
            if link:
                link = link.split("#")[0]
                link = link.split("?")[0]
                link = link.rstrip("/")
            if link:
                collected_links.append(link)
    except NoSuchElementException:
        # Handle the case when the class name is not found
        pass
Nav_links = set(collected_links)
all_links = set(all_links)
link_not_in_nav = all_links - Nav_links

#for pydantic validator on links.
from pydantic import BaseModel, HttpUrl
class LinkModel(BaseModel):
    url: HttpUrl

# Function to validate a set of links using the LinkModel
def Check_valid_links(value):
    valid = []
    for link in value:
        try:
            validated_link = LinkModel(url=link)
            valid.append(validated_link.url)
        except ValueError as e:
            print(f"Invalid link: {link}. Error: {e}")
            pass
    
    return valid

# Validate the links
validated_links = Check_valid_links(link_not_in_nav)
# For links write into json file.
j = json.dumps(validated_links)
f = open("links.json", "w")
f.write(j)
f.close()
# For Text write into json file.
j = json.dumps(all_text)
f = open("texts.json", "w")
f.write(j)
f.close()


# Creating NLP Pipelining through hugging face model.
from transformers import AutoTokenizer, AutoModelForTokenClassification, AutoModel
from transformers import pipeline
import torch

tokenizer = AutoTokenizer.from_pretrained("yanekyuk/bert-uncased-keyword-extractor")
model = AutoModelForTokenClassification.from_pretrained(
    "yanekyuk/bert-uncased-keyword-extractor"
)

nlp = pipeline("ner", model=model, tokenizer=tokenizer)


def extract_keywords(text):
    """
    Extract keywords and construct them back from tokens
    """
    result = list()
    keyword = ""
    for token in nlp(text):
        if token["entity"] == "I-KEY":
            keyword += (
                token["word"][2:]
                if token["word"].startswith("##")
                else f" {token['word']}"
            )
        else:
            if keyword:
                result.append(keyword)
            keyword = token["word"]
    # Add the last keyword
    result.append(keyword)
    return list(set(result))
keywords = extract_keywords(all_text)


# For calculating Embedding of all_text.
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
def generate_embeddings(text):
    embeddings = model.encode(text)
    return [float(x) for x in embeddings.tolist()]

embdedding = generate_embeddings(all_text)
print(embdedding)




# Import to Neo4j Connection to Neo4j database.
from graphdatascience import GraphDataScience

host = "bolt://54.158.242.240:7687"
user = "neo4j"
password = "launch-mention-fishes"

gds = GraphDataScience(host, auth=(user, password))

# Assuming 'validated_links' is a list of URLs and 'keywords' is a list of extracted keywords
# Create Page nodes
for link in validated_links:
    gds.run_cypher(
        f"""
        MERGE (p:Page {{url: "{link}"}})
        """
    )

# Create Keyword nodes (if not already created)
for keyword in keywords:
    gds.run_cypher(
        f"""
        MERGE (k:Keyword {{name: "{keyword}"}})
        """
    )

# Create relationships between Page and Keyword nodes
for link in validated_links:
    for keyword in keywords:
        gds.run_cypher(
            f"""
            MATCH (p:Page {{url: "{link}"}})
            MATCH (k:Keyword {{name: "{keyword}"}})
            MERGE (p)-[:MENTIONS]->(k)
            """
        )


# Add embeddings as properties to Page nodes
for i, link in enumerate(validated_links):
    gds.run_cypher(
        f"""
        MATCH (p:Page {{url: "{link}"}})
        SET p.embedding = {embdedding[i]}
        """
    )

# Add embeddings as properties to Keyword nodes
for i, keyword in enumerate(keywords):
    gds.run_cypher(
        f"""
        MATCH (k:Keyword {{name: "{keyword}"}})
        SET k.embedding = {embdedding[i]}
        """
    )

#Close the driver.
driver.quit()

