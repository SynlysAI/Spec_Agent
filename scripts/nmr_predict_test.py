from app.services.nmr_server_service import nmr_server_service

h_shifts_input = "-0.13,1.10,3.68,7.14"
h_split_input = "s,t,m,s"
c_shifts_input = ""
formula = ""
allowed_elements = ""
candidates = ""
# reverse_res = nmr_server_service.reverse_predict(
#     h_shifts_input,
#     h_split_input,
#     c_shifts_input,
#     formula,
#     allowed_elements,
#     candidates,
# )

# reverse_predict_smiles = []
# for info in reverse_res[:10]:
#     reverse_predict_smiles.append(info["smiles"])
#
# print(reverse_predict_smiles)

database_predict_smiles = []
database_res = nmr_server_service.database_search(
    h_shifts_input,
    h_split_input,
    c_shifts_input,
    num_search=500,
    topk=10,
    allowed_elements="",
)

for info in database_res:
    database_predict_smiles.append(info["smiles"])
print(database_predict_smiles)
print(database_predict_smiles)
print(database_predict_smiles)
print(database_predict_smiles)